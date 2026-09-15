import sys
from src.logger import logger

def error_message_detail(error: Exception, error_detail) -> str:

    _, _, exc_tb = error_detail.exc_info()

    if exc_tb is not None:
        file_name = exc_tb.tb_frame.f_code.co_filename
        line_number = exc_tb.tb_lineno
        error_message = (
            f"Error occurred in python script: [{file_name}] "
            f"at line number [{line_number}]: {str(error)}"
        )
    else:
        error_message = f"Error occurred: {str(error)}"

    logger.error(error_message)
    return error_message


class MyException(Exception):

    def __init__(self, error_message: Exception, error_detail):

        super().__init__(str(error_message))
        self.error_message = error_message_detail(error_message, error_detail)

    def __str__(self) -> str:
        return self.error_message
