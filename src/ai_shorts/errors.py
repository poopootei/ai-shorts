class AiShortsError(Exception):
    """利用者に見せるエラー。CLI はメッセージだけを表示して止まる。"""


class ConfigError(AiShortsError):
    pass


class ExternalToolError(AiShortsError):
    """VOICEVOX・ffmpeg などの外部ツールに接続できない、または失敗した。"""


class StoryError(AiShortsError):
    pass


class StoryTooLongError(StoryError):
    pass
