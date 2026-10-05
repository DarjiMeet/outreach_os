class WebsiteFetchError(Exception):
    pass


class WebsiteBlockedError(WebsiteFetchError):
    pass


class WebsiteNotFoundError(WebsiteFetchError):
    pass


class WebsiteTemporaryError(WebsiteFetchError):
    pass