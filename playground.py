from pathlib import Path

from roam_to_git import formatter
from roam_to_git.fs import save_files

if __name__ == "__main__":

    contents = formatter.read_markdown_directory(Path().absolute() / "markdown")

    formatted = formatter.format_markdown(contents)

    save_files("formatted", Path().absolute() / "formatted", formatted)
