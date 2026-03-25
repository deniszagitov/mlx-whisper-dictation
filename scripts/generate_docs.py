"""Генерирует страницы MkDocs из docstring в исходном коде проекта."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"


@dataclass
class FunctionDoc:
    """Описывает документацию для функции или метода."""

    name: str
    signature: str
    docstring: str
    is_private: bool = False


@dataclass
class ClassDoc:
    """Описывает документацию для класса и его методов."""

    name: str
    docstring: str
    methods: list[FunctionDoc]
    properties: list[FunctionDoc]


@dataclass
class ModuleDoc:
    """Описывает документацию для Python-модуля."""

    title: str
    path: Path
    docstring: str
    constants: list[tuple[str, str]]
    functions: list[FunctionDoc]
    classes: list[ClassDoc]


def _render_annotation(node: ast.AST | None) -> str:
    """Возвращает строковое представление аннотации или значения по AST."""
    if node is None:
        return ""
    return ast.unparse(node)


def _build_signature(node: ast.FunctionDef | ast.AsyncFunctionDef, *, drop_first_arg: bool = False) -> str:
    """Собирает человекочитаемую сигнатуру функции из AST."""
    args = node.args
    parts: list[str] = []

    positional = [*args.posonlyargs, *args.args]
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)

    for index, (arg, default) in enumerate(zip(positional, defaults, strict=True)):
        if drop_first_arg and index == 0 and arg.arg in {"self", "cls"}:
            continue
        item = arg.arg
        if arg.annotation is not None:
            item += f": {_render_annotation(arg.annotation)}"
        if default is not None:
            item += f" = {_render_annotation(default)}"
        parts.append(item)
        if args.posonlyargs and index == len(args.posonlyargs) - 1:
            parts.append("/")

    if args.vararg is not None:
        item = f"*{args.vararg.arg}"
        if args.vararg.annotation is not None:
            item += f": {_render_annotation(args.vararg.annotation)}"
        parts.append(item)
    elif args.kwonlyargs:
        parts.append("*")

    for kwarg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        item = kwarg.arg
        if kwarg.annotation is not None:
            item += f": {_render_annotation(kwarg.annotation)}"
        if default is not None:
            item += f" = {_render_annotation(default)}"
        parts.append(item)

    if args.kwarg is not None:
        item = f"**{args.kwarg.arg}"
        if args.kwarg.annotation is not None:
            item += f": {_render_annotation(args.kwarg.annotation)}"
        parts.append(item)

    signature = f"({', '.join(parts)})"
    if node.returns is not None:
        signature += f" -> {_render_annotation(node.returns)}"
    return signature


def _collect_constants(module: ast.Module) -> list[tuple[str, str]]:
    """Извлекает простые константы верхнего уровня из модуля."""
    constants: list[tuple[str, str]] = []
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
            continue
        name = statement.targets[0].id
        if not name.isupper():
            continue
        try:
            value = ast.literal_eval(statement.value)
        except Exception:
            value_repr = _render_annotation(statement.value)
        else:
            value_repr = repr(value)
        constants.append((name, value_repr))
    return constants


def _collect_methods(nodes: Iterable[ast.stmt]) -> tuple[list[FunctionDoc], list[FunctionDoc]]:
    """Извлекает методы и свойства класса."""
    methods: list[FunctionDoc] = []
    properties: list[FunctionDoc] = []

    for node in nodes:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        docstring = ast.get_docstring(node)
        if not docstring and node.name != "__init__":
            continue

        decorators = {_render_annotation(decorator) for decorator in node.decorator_list}
        item = FunctionDoc(
            name=node.name,
            signature=_build_signature(node, drop_first_arg=True),
            docstring=docstring or "Конструктор класса.",
            is_private=node.name.startswith("_") and node.name != "__init__",
        )
        if "property" in decorators:
            properties.append(item)
        else:
            methods.append(item)

    return methods, properties


def _parse_module(path: Path, title: str) -> ModuleDoc:
    """Разбирает Python-модуль и извлекает его docstring-структуру."""
    module = ast.parse(path.read_text(encoding="utf-8"))
    functions: list[FunctionDoc] = []
    classes: list[ClassDoc] = []

    for node in module.body:
        if isinstance(node, ast.ClassDef):
            methods, properties = _collect_methods(node.body)
            classes.append(
                ClassDoc(
                    name=node.name,
                    docstring=ast.get_docstring(node) or "Документация класса пока не описана.",
                    methods=methods,
                    properties=properties,
                )
            )
            continue

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            docstring = ast.get_docstring(node)
            if not docstring:
                continue
            functions.append(
                FunctionDoc(
                    name=node.name,
                    signature=_build_signature(node),
                    docstring=docstring,
                    is_private=node.name.startswith("_"),
                )
            )

    return ModuleDoc(
        title=title,
        path=path,
        docstring=ast.get_docstring(module) or "Документация модуля пока не описана.",
        constants=_collect_constants(module),
        functions=functions,
        classes=classes,
    )


def _write(path: str, content: str) -> None:
    """Записывает сгенерированный Markdown-файл в каталог docs/."""
    file_path = DOCS_DIR / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _render_function(function: FunctionDoc, *, level: int = 2) -> str:
    """Рендерит раздел документации для функции или метода."""
    marker = "_Внутренняя функция._\n\n" if function.is_private else ""
    heading = "#" * level
    return f"{heading} `{function.name}`\n\n```python\n{function.name}{function.signature}\n```\n\n{marker}{function.docstring}\n"


def _render_class(class_doc: ClassDoc) -> str:
    """Рендерит раздел документации для класса."""
    parts = [f"## `{class_doc.name}`\n\n{class_doc.docstring}\n"]

    if class_doc.properties:
        parts.append("### Свойства\n")
        for item in class_doc.properties:
            parts.append(_render_function(item, level=4))

    if class_doc.methods:
        parts.append("### Методы\n")
        for item in class_doc.methods:
            parts.append(_render_function(item, level=4))

    return "\n".join(parts)


def _render_module(module_doc: ModuleDoc) -> str:
    """Рендерит полноценную страницу API для модуля."""
    public_functions = [item for item in module_doc.functions if not item.is_private]
    private_functions = [item for item in module_doc.functions if item.is_private]

    lines = [
        f"# {module_doc.title}",
        "",
        f"Исходный файл: `{module_doc.path.name}`",
        "",
        module_doc.docstring,
        "",
    ]

    if module_doc.constants:
        lines.extend(["## Константы", ""])
        for name, value in module_doc.constants:
            lines.append(f"- `{name}` = `{value}`")
        lines.append("")

    if module_doc.classes:
        lines.extend(["## Классы", ""])
        for item in module_doc.classes:
            lines.append(_render_class(item))

    if public_functions:
        lines.extend(["## Публичные функции", ""])
        for item in public_functions:
            lines.append(_render_function(item, level=3))

    if private_functions:
        lines.extend(["## Внутренние функции", ""])
        for item in private_functions:
            lines.append(_render_function(item, level=3))

    return "\n".join(lines)


def main() -> None:
    """Генерирует главную страницу и API-страницы для MkDocs."""
    runtime_module = _parse_module(ROOT / "whisper-dictation.py", "Runtime API")
    setup_module = _parse_module(ROOT / "setup.py", "API сборки")

    overview = "\n".join(
        [
            "# Dictator",
            "",
            "Этот сайт собирается автоматически из docstring и структуры Python-кода в репозитории.",
            "",
            runtime_module.docstring,
            "",
            "## Что уже доступно",
            "",
            "- Полное описание текущего runtime-модуля приложения.",
            "- Автогенерируемая страница с кодом сборки через py2app.",
            "- Архитектурная диаграмма основных потоков приложения.",
            "",
            "## Разделы",
            "",
            "- [Runtime API](api/runtime.md)",
            "- [API сборки](api/setup.md)",
            "- [Архитектура](architecture.md)",
        ]
    )

    _write("index.md", overview)
    _write("api/runtime.md", _render_module(runtime_module))
    _write("api/setup.md", _render_module(setup_module))


def on_pre_build(*_args, **_kwargs) -> None:
    """Обновляет автогенерируемые страницы перед сборкой MkDocs."""
    main()


if __name__ == "__main__":
    main()
