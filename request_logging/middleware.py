import logging
import re

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.utils.termcolors import colorize

DEFAULT_LOG_LEVEL = logging.DEBUG
DEFAULT_COLORIZE = True
DEFAULT_MAX_BODY_LENGTH = 50000  # log no more than 3k bytes of content
SETTING_NAMES = {
    'log_level': 'REQUEST_LOGGING_DATA_LOG_LEVEL',
    'colorize': 'REQUEST_LOGGING_DISABLE_COLORIZE',
    'max_body_length': 'REQUEST_LOGGING_MAX_BODY_LENGTH'
}
request_logger = logging.getLogger('django.request')


class Logger:
    def log(self, level, msg):
        request_logger.log(level, str(msg))

    def log_error(self, level, msg):
        self.log(level, msg)


class ColourLogger(Logger):
    def __init__(self, log_colour, log_error_colour):
        self.log_colour = log_colour
        self.log_error_colour = log_error_colour

    def log(self, level, msg):
        colour = self.log_error_colour if level >= logging.ERROR else self.log_colour
        self._log(level, msg, colour)

    def log_error(self, level, msg):
        # Forces colour to be log_error_colour no matter what level is
        self._log(level, msg, self.log_error_colour)

    def _log(self, level, msg, colour):
        request_logger.log(level, colorize(str(msg), fg=colour))


class LoggingMiddleware(MiddlewareMixin):
    def __init__(self, *args, **kwargs):
        super(MiddlewareMixin, self).__init__(*args, **kwargs)

        self.log_level = getattr(settings, SETTING_NAMES['log_level'], DEFAULT_LOG_LEVEL)
        if self.log_level not in [logging.NOTSET, logging.DEBUG, logging.INFO,
                                  logging.WARNING, logging.ERROR, logging.CRITICAL]:
            raise ValueError("Unknown log level({}) in setting({})".format(self.log_level, SETTING_NAMES['log_level']))

        enable_colorize = getattr(settings, SETTING_NAMES['colorize'], DEFAULT_COLORIZE)
        if type(enable_colorize) is not bool:
            raise ValueError(
                "{} should be boolean. {} is not boolean.".format(SETTING_NAMES['colorize'], enable_colorize)
            )

        self.max_body_length = getattr(settings, SETTING_NAMES['max_body_length'], DEFAULT_MAX_BODY_LENGTH)
        if type(self.max_body_length) is not int:
            raise ValueError(
                "{} should be int. {} is not int.".format(SETTING_NAMES['max_body_length'], self.max_body_length)
            )

        self.logger = ColourLogger("cyan", "magenta") if enable_colorize else Logger()

    def process_request(self, request):
        method_path = "{} {}".format(request.method, request.get_full_path())
        self.logger.log(logging.INFO, method_path)

        headers = {k: v for k, v in request.META.items() if k.startswith('HTTP_')}

        if headers:
            self.logger.log(self.log_level, headers)
        if request.body:
            self.logger.log(self.log_level, self._chunked_to_max(request.body))

    def process_response(self, request, response):
        resp_log = "{} {} - {}".format(request.method, request.get_full_path(), response.status_code)

        if response.status_code in range(400, 600):
            self.logger.log_error(logging.INFO, resp_log)
            self._log_resp(logging.ERROR, response)
        else:
            self.logger.log(logging.INFO, resp_log)
            self._log_resp(self.log_level, response)

        return response

    def _log_resp(self, level, response):
        if re.match('^application/json', response.get('Content-Type', ''), re.I):
            self.logger.log(level, response._headers)
            self.logger.log(level, self._chunked_to_max(response.content))

    def _chunked_to_max(self, msg):
        if len(msg) > self.max_body_length:
            return "{0}\n...\n".format(msg[0:self.max_body_length])

        return msg
