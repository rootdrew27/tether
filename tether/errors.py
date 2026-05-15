class TetherError(Exception):
    pass


class NotAGitRepoError(TetherError):
    pass


class NotATetherProjectError(TetherError):
    pass


class TetherNotFoundError(TetherError):
    pass


class InvalidTetherError(TetherError):
    pass


class GitError(TetherError):
    pass


class AlreadyInitializedError(TetherError):
    pass
