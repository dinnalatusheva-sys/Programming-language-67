import ast
import sys


class ConvertError(Exception):
    pass


class PythonTo67(ast.NodeVisitor):
    def __init__(self):
        self.lines = []
        self.indent = 0

    def emit(self, text: str):
        self.lines.append("    " * self.indent + text)

    def convert(self, source: str) -> str:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ConvertError(f"Ошибка синтаксиса Python: {exc}") from exc
        self.visit(tree)
        return "\n".join(self.lines) + ("\n" if self.lines else "")

    def visit_Module(self, node: ast.Module):
        for stmt in node.body:
            self.visit(stmt)

    def visit_Assign(self, node: ast.Assign):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise ConvertError("Поддерживается только простое присваивание: name = expr")
        name = node.targets[0].id
        value = self.expr(node.value)
        self.emit(f"пусть {name} = {value}")

    def visit_Expr(self, node: ast.Expr):
        if isinstance(node.value, ast.Call) and self._is_name(node.value.func, "print"):
            args = node.value.args
            if len(args) != 1:
                raise ConvertError("print() поддерживает ровно один аргумент")
            self.emit(f"вывод {self.expr(args[0])}")
            return
        raise ConvertError(f"Неподдерживаемое выражение: {ast.dump(node, include_attributes=False)}")

    def visit_If(self, node: ast.If):
        cond = self.cond(node.test)
        self.emit(f"если {cond} то")
        self.indent += 1
        for stmt in node.body:
            self.visit(stmt)
        self.indent -= 1
        self.emit("иначе")
        self.indent += 1
        for stmt in node.orelse:
            self.visit(stmt)
        self.indent -= 1
        self.emit("конец")

    def visit_While(self, node: ast.While):
        if node.orelse:
            raise ConvertError("while ... else не поддерживается в языке 67")
        cond = self.cond(node.test)
        self.emit(f"пока {cond} делать")
        self.indent += 1
        for stmt in node.body:
            self.visit(stmt)
        self.indent -= 1
        self.emit("конец")

    def visit_Break(self, node: ast.Break):
        self.emit("стоп")

    def visit_Continue(self, node: ast.Continue):
        self.emit("продолжить")

    def visit_AugAssign(self, node: ast.AugAssign):
        if not isinstance(node.target, ast.Name):
            raise ConvertError("Поддерживается только x += y / x -= y ...")
        op = self._bin_op(node.op)
        left = node.target.id
        right = self.expr(node.value)
        self.emit(f"пусть {left} = {left} {op} {right}")

    def visit_Pass(self, node: ast.Pass):
        # В языке 67 нет pass, безопасно пропускаем.
        return

    def visit_For(self, node: ast.For):
        raise ConvertError("for не поддерживается. Используйте while.")

    def visit_FunctionDef(self, node: ast.FunctionDef):
        raise ConvertError("Функции не поддерживаются в языке 67.")

    def visit_Return(self, node: ast.Return):
        raise ConvertError("return не поддерживается в языке 67.")

    def generic_visit(self, node):
        raise ConvertError(f"Неподдерживаемая инструкция: {type(node).__name__}")

    def cond(self, node: ast.AST) -> str:
        if isinstance(node, ast.BoolOp):
            op = "и" if isinstance(node.op, ast.And) else "или"
            parts = [self.cond(v) for v in node.values]
            return f" {op} ".join(f"({p})" for p in parts)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return f"не ({self.cond(node.operand)})"
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise ConvertError("Цепочки сравнений не поддерживаются (например 1 < x < 5)")
            left = self.expr(node.left)
            op = self._cmp_op(node.ops[0])
            right = self.expr(node.comparators[0])
            return f"{left} {op} {right}"
        if isinstance(node, ast.NameConstant) and isinstance(node.value, bool):
            return "1 == 1" if node.value else "1 == 0"
        return self.expr(node)

    def expr(self, node: ast.AST) -> str:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "1" if node.value else "0"
            if isinstance(node.value, int):
                return str(node.value)
            if isinstance(node.value, str):
                escaped = node.value.replace('"', '\\"')
                return f"\"{escaped}\""
            raise ConvertError("Поддерживаются только int/str/bool константы")
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.BinOp):
            left = self.expr(node.left)
            op = self._bin_op(node.op)
            right = self.expr(node.right)
            return f"({left} {op} {right})"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return f"-({self.expr(node.operand)})"
        if isinstance(node, ast.Call) and self._is_name(node.func, "input"):
            if node.args:
                raise ConvertError("input() с аргументом не поддерживается")
            tmp_name = "__input_tmp"
            raise ConvertError(
                "Нельзя использовать input() внутри выражения. "
                "Сделайте отдельно: x = input()"
            )
        if isinstance(node, ast.Call) and self._is_name(node.func, "int"):
            if len(node.args) != 1:
                raise ConvertError("int() поддерживает ровно один аргумент")
            return self.expr(node.args[0])
        raise ConvertError(f"Неподдерживаемое выражение: {ast.dump(node, include_attributes=False)}")

    def _cmp_op(self, op: ast.cmpop) -> str:
        mapping = {
            ast.Eq: "==",
            ast.NotEq: "!=",
            ast.Lt: "<",
            ast.Gt: ">",
            ast.LtE: "<=",
            ast.GtE: ">=",
        }
        for py_op, text in mapping.items():
            if isinstance(op, py_op):
                return text
        raise ConvertError(f"Неподдерживаемый оператор сравнения: {type(op).__name__}")

    def _bin_op(self, op: ast.operator) -> str:
        mapping = {
            ast.Add: "+",
            ast.Sub: "-",
            ast.Mult: "*",
            ast.Div: "/",
            ast.FloorDiv: "/",
        }
        for py_op, text in mapping.items():
            if isinstance(op, py_op):
                return text
        raise ConvertError(f"Неподдерживаемый оператор: {type(op).__name__}")

    @staticmethod
    def _is_name(node: ast.AST, name: str) -> bool:
        return isinstance(node, ast.Name) and node.id == name


def preprocess_input_assignments(source: str) -> str:
    lines = source.splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and "input()" in stripped:
            parts = stripped.split("=", 1)
            left = parts[0].strip()
            right = parts[1].strip()
            if right == "input()":
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{left} = __py67_input__()")
                continue
        out.append(line)
    return "\n".join(out) + ("\n" if source.endswith("\n") else "")


class InputRewriter(ast.NodeTransformer):
    def visit_Assign(self, node: ast.Assign):
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "__py67_input__"
        ):
            name = node.targets[0].id
            return ast.Expr(value=ast.Call(func=ast.Name(id="__py67_input_stmt__", ctx=ast.Load()), args=[ast.Constant(name)], keywords=[]))
        return self.generic_visit(node)


class PythonTo67WithInput(PythonTo67):
    def visit_Expr(self, node: ast.Expr):
        if isinstance(node.value, ast.Call) and self._is_name(node.value.func, "__py67_input_stmt__"):
            if len(node.value.args) != 1 or not isinstance(node.value.args[0], ast.Constant) or not isinstance(node.value.args[0].value, str):
                raise ConvertError("Внутренняя ошибка обработки input()")
            self.emit(f"ввод {node.value.args[0].value}")
            return
        return super().visit_Expr(node)


def convert_python_to_67(source: str) -> str:
    pre = preprocess_input_assignments(source)
    tree = ast.parse(pre)
    tree = InputRewriter().visit(tree)
    ast.fix_missing_locations(tree)
    converter = PythonTo67WithInput()
    converter.visit(tree)
    return "\n".join(converter.lines) + ("\n" if converter.lines else "")


def main():
    if len(sys.argv) != 3:
        print("Использование: python core/py_to_67.py <input.py> <output.67>")
        raise SystemExit(1)
    in_path = sys.argv[1]
    out_path = sys.argv[2]
    try:
        with open(in_path, "r", encoding="utf-8") as f:
            source = f.read()
        result = convert_python_to_67(source)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Готово: {out_path}")
    except FileNotFoundError:
        print(f"Файл не найден: {in_path}")
        raise SystemExit(1)
    except ConvertError as exc:
        print(f"Ошибка конвертации: {exc}")
        raise SystemExit(1)
    except SyntaxError as exc:
        print(f"Ошибка синтаксиса Python: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
