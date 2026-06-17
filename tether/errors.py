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


class LocatorError(TetherError):
    """A section locator could not be applied. Base for the cases below."""


class UnsupportedLocatorError(LocatorError):
    """The locator names a language or kind this build cannot parse."""


class LocatorUnresolvedError(LocatorError):
    """The selector matches no node in the file (renamed/removed region)."""


class AmbiguousLocatorError(LocatorError):
    """The selector matches more than one node at some path segment."""
