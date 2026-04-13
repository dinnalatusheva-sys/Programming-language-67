import sys
from dataclasses import dataclass


class Lang67Error(Exception):
    pass


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


@dataclass
class Token:
    kind: str
    value: str
    pos: int


class Lexer:
    KEYWORDS = {
        "пусть": "LET",
        "вывод": "PRINT",
        "ввод": "INPUT",
        "если": "IF",
        "то": "THEN",
        "иначе": "ELSE",
        "конец": "END",
        "пока": "WHILE",
        "делать": "DO",
        "стоп": "BREAK",
        "продолжить": "CONTINUE",
        "и": "AND",
        "или": "OR",
        "не": "NOT",
    }

    SINGLE = {
        "+": "PLUS",
        "-": "MINUS",
        "*": "STAR",
        "/": "SLASH",
        "(": "LPAREN",
        ")": "RPAREN",
        "=": "ASSIGN",
    }

    def __init__(self, text: str):
        self.text = text
        self.i = 0

    def tokenize(self):
        tokens = []
        while self.i < len(self.text):
            ch = self.text[self.i]
            if ch in " \t\r":
                self.i += 1
                continue
            if ch == "\n":
                tokens.append(Token("NEWLINE", "\n", self.i))
                self.i += 1
                continue
            if ch == "#":
                while self.i < len(self.text) and self.text[self.i] != "\n":
                    self.i += 1
                continue
            if ch == '"':
                start = self.i
                self.i += 1
                chars = []
                while self.i < len(self.text) and self.text[self.i] != '"':
                    chars.append(self.text[self.i])
                    self.i += 1
                if self.i >= len(self.text):
                    raise Lang67Error(f"Незакрытая строка в позиции {start}")
                self.i += 1
                tokens.append(Token("STRING", "".join(chars), start))
                continue
            if ch.isdigit():
                start = self.i
                while self.i < len(self.text) and self.text[self.i].isdigit():
                    self.i += 1
                tokens.append(Token("NUMBER", self.text[start:self.i], start))
                continue
            if ch.isalpha() or ch == "_":
                start = self.i
                while self.i < len(self.text) and (self.text[self.i].isalnum() or self.text[self.i] == "_"):
                    self.i += 1
                value = self.text[start:self.i]
                kind = self.KEYWORDS.get(value, "IDENT")
                tokens.append(Token(kind, value, start))
                continue
            two = self.text[self.i:self.i + 2]
            if two in ("==", "!=", "<=", ">="):
                tokens.append(Token("OP", two, self.i))
                self.i += 2
                continue
            if ch in ("<", ">"):
                tokens.append(Token("OP", ch, self.i))
                self.i += 1
                continue
            if ch in self.SINGLE:
                tokens.append(Token(self.SINGLE[ch], ch, self.i))
                self.i += 1
                continue
            raise Lang67Error(f"Неизвестный символ '{ch}' в позиции {self.i}")
        tokens.append(Token("EOF", "", self.i))
        return tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    def cur(self):
        return self.tokens[self.i]

    def eat(self, kind):
        token = self.cur()
        if token.kind != kind:
            raise Lang67Error(f"Ожидался токен {kind}, получен {token.kind} в позиции {token.pos}")
        self.i += 1
        return token

    def skip_newlines(self):
        while self.cur().kind == "NEWLINE":
            self.i += 1

    def parse(self):
        stmts = []
        self.skip_newlines()
        while self.cur().kind != "EOF":
            stmts.append(self.statement())
            self.skip_newlines()
        return ("block", stmts)

    def statement(self):
        token = self.cur()
        if token.kind == "LET":
            self.eat("LET")
            name = self.eat("IDENT").value
            self.eat("ASSIGN")
            expr = self.expr()
            return ("let", name, expr)
        if token.kind == "PRINT":
            self.eat("PRINT")
            return ("print", self.expr())
        if token.kind == "INPUT":
            self.eat("INPUT")
            name = self.eat("IDENT").value
            return ("input", name)
        if token.kind == "IF":
            return self.if_stmt()
        if token.kind == "WHILE":
            return self.while_stmt()
        if token.kind == "BREAK":
            self.eat("BREAK")
            return ("break",)
        if token.kind == "CONTINUE":
            self.eat("CONTINUE")
            return ("continue",)
        raise Lang67Error(f"Неожиданный токен {token.kind} в позиции {token.pos}")

    def if_stmt(self):
        self.eat("IF")
        cond = self.condition()
        self.eat("THEN")
        self.skip_newlines()
        then_stmts = []
        else_stmts = []
        while self.cur().kind not in ("ELSE", "END", "EOF"):
            then_stmts.append(self.statement())
            self.skip_newlines()
        if self.cur().kind == "ELSE":
            self.eat("ELSE")
            self.skip_newlines()
            while self.cur().kind not in ("END", "EOF"):
                else_stmts.append(self.statement())
                self.skip_newlines()
        self.eat("END")
        return ("if", cond, ("block", then_stmts), ("block", else_stmts))

    def while_stmt(self):
        self.eat("WHILE")
        cond = self.condition()
        self.eat("DO")
        self.skip_newlines()
        body = []
        while self.cur().kind not in ("END", "EOF"):
            body.append(self.statement())
            self.skip_newlines()
        self.eat("END")
        return ("while", cond, ("block", body))

    def condition(self):
        return self.bool_or()

    def bool_or(self):
        node = self.bool_and()
        while self.cur().kind == "OR":
            self.eat("OR")
            node = ("bool_or", node, self.bool_and())
        return node

    def bool_and(self):
        node = self.bool_not()
        while self.cur().kind == "AND":
            self.eat("AND")
            node = ("bool_and", node, self.bool_not())
        return node

    def bool_not(self):
        if self.cur().kind == "NOT":
            self.eat("NOT")
            return ("bool_not", self.bool_not())
        return self.bool_atom()

    def bool_atom(self):
        if self.cur().kind == "LPAREN":
            self.eat("LPAREN")
            node = self.condition()
            self.eat("RPAREN")
            return node
        left = self.expr()
        op = self.eat("OP").value
        right = self.expr()
        return ("cmp", op, left, right)

    def expr(self):
        node = self.term()
        while self.cur().kind in ("PLUS", "MINUS"):
            op = self.cur().value
            self.i += 1
            node = ("binop", op, node, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.cur().kind in ("STAR", "SLASH"):
            op = self.cur().value
            self.i += 1
            node = ("binop", op, node, self.factor())
        return node

    def factor(self):
        token = self.cur()
        if token.kind == "NUMBER":
            self.i += 1
            return ("num", int(token.value))
        if token.kind == "STRING":
            self.i += 1
            return ("str", token.value)
        if token.kind == "IDENT":
            self.i += 1
            return ("var", token.value)
        if token.kind == "LPAREN":
            self.eat("LPAREN")
            node = self.expr()
            self.eat("RPAREN")
            return node
        if token.kind == "MINUS":
            self.eat("MINUS")
            return ("neg", self.factor())
        raise Lang67Error(f"Неожиданный токен {token.kind} в позиции {token.pos}")


class Interpreter:
    def __init__(self):
        self.env = {}

    def run(self, node):
        kind = node[0]
        if kind == "block":
            for stmt in node[1]:
                self.run(stmt)
            return None
        if kind == "let":
            _, name, expr = node
            self.env[name] = self.eval_expr(expr)
            return None
        if kind == "print":
            print(self.eval_expr(node[1]))
            return None
        if kind == "input":
            _, name = node
            raw_value = input()
            try:
                self.env[name] = int(raw_value)
            except ValueError:
                self.env[name] = raw_value
            return None
        if kind == "if":
            _, cond, then_block, else_block = node
            if self.eval_cond(cond):
                self.run(then_block)
            else:
                self.run(else_block)
            return None
        if kind == "while":
            _, cond, body = node
            while self.eval_cond(cond):
                try:
                    self.run(body)
                except ContinueSignal:
                    continue
                except BreakSignal:
                    break
            return None
        if kind == "break":
            raise BreakSignal()
        if kind == "continue":
            raise ContinueSignal()
        raise Lang67Error(f"Неизвестный тип инструкции {kind}")

    def eval_cond(self, node):
        kind = node[0]
        if kind == "cmp":
            _, op, left, right = node
            lv = self.eval_expr(left)
            rv = self.eval_expr(right)
            if op == "==":
                return lv == rv
            if op == "!=":
                return lv != rv
            if op == "<":
                return lv < rv
            if op == ">":
                return lv > rv
            if op == "<=":
                return lv <= rv
            if op == ">=":
                return lv >= rv
            raise Lang67Error(f"Неизвестный оператор сравнения {op}")
        if kind == "bool_and":
            return self.eval_cond(node[1]) and self.eval_cond(node[2])
        if kind == "bool_or":
            return self.eval_cond(node[1]) or self.eval_cond(node[2])
        if kind == "bool_not":
            return not self.eval_cond(node[1])
        raise Lang67Error(f"Неизвестный тип условия {kind}")

    def eval_expr(self, node):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "str":
            return node[1]
        if kind == "var":
            name = node[1]
            if name not in self.env:
                raise Lang67Error(f"Неизвестная переменная '{name}'")
            return self.env[name]
        if kind == "neg":
            value = self.eval_expr(node[1])
            if not isinstance(value, int):
                raise Lang67Error("Унарный минус работает только с числами")
            return -value
        if kind == "binop":
            _, op, left, right = node
            lv = self.eval_expr(left)
            rv = self.eval_expr(right)
            if op == "+":
                if isinstance(lv, int) and isinstance(rv, int):
                    return lv + rv
                if isinstance(lv, str) and isinstance(rv, str):
                    return lv + rv
                raise Lang67Error("Сложение возможно только число+число или строка+строка")
            if op == "-":
                if not isinstance(lv, int) or not isinstance(rv, int):
                    raise Lang67Error("Вычитание возможно только для чисел")
                return lv - rv
            if op == "*":
                if not isinstance(lv, int) or not isinstance(rv, int):
                    raise Lang67Error("Умножение возможно только для чисел")
                return lv * rv
            if op == "/":
                if not isinstance(lv, int) or not isinstance(rv, int):
                    raise Lang67Error("Деление возможно только для чисел")
                if rv == 0:
                    raise Lang67Error("Деление на ноль")
                return lv // rv
        raise Lang67Error(f"Неизвестный тип выражения {kind}")


def execute(source: str):
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    interpreter = Interpreter()
    try:
        interpreter.run(ast)
    except BreakSignal:
        raise Lang67Error("Команда 'стоп' может использоваться только внутри цикла")
    except ContinueSignal:
        raise Lang67Error("Команда 'продолжить' может использоваться только внутри цикла")


def main():
    if len(sys.argv) != 2:
        print("Использование: python core/lang67.py <файл.67>")
        raise SystemExit(1)
    path = sys.argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        execute(source)
    except FileNotFoundError:
        print(f"Файл не найден: {path}")
        raise SystemExit(1)
    except Lang67Error as e:
        print(f"Ошибка языка 67: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
