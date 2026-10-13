from loguru import logger
# The desktop worker owns the only sink, including secret redaction.
logger.remove()
