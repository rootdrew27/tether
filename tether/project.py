from pathlib import Path

from .errors import AlreadyInitializedError, NotAGitRepoError, NotATetherProjectError
from .git import run_git, run_git_checked

PROJECT_DIR_NAME = ".tether"
TETHERS_SUBDIR = "tethers"


def find_project_root(start: Path) -> Path:
    start = start.resolve()
    for candidate in [start, *start.parents]:
        if (candidate / PROJECT_DIR_NAME).is_dir():
            return candidate
    raise NotATetherProjectError(
        f"No {PROJECT_DIR_NAME}/ directory found at {start} or any ancestor"
    )


def is_inside_git_work_tree(path: Path) -> bool:
    result = run_git(["rev-parse", "--is-inside-work-tree"], cwd=path)
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_toplevel(path: Path) -> Path:
    result = run_git_checked(
        ["rev-parse", "--show-toplevel"],
        cwd=path,
        error_prefix=f"{path} is not inside a git work tree",
        error_cls=NotAGitRepoError,
    )
    return Path(result.stdout.strip())


def init_project(start: Path) -> Path:
    if not is_inside_git_work_tree(start):
        raise NotAGitRepoError(
            f"{start} is not inside a git work tree. Run `git init` first."
        )
    root = git_toplevel(start)
    tether_dir = root / PROJECT_DIR_NAME
    tethers_dir = tether_dir / TETHERS_SUBDIR
    already = tether_dir.exists()
    tethers_dir.mkdir(parents=True, exist_ok=True)
    if already and not tethers_dir.is_dir():
        raise AlreadyInitializedError(
            f"{tether_dir} exists but {TETHERS_SUBDIR} is not a directory"
        )
    return root


def tethers_dir(project_root: Path) -> Path:
    return project_root / PROJECT_DIR_NAME / TETHERS_SUBDIR
