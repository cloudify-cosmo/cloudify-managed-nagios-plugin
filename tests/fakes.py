from managed_nagios_plugin._compat import text_type
from contextlib import contextmanager
from pprint import pprint


class FakeLogger(object):
    def __init__(self):
        self.messages = {
            'debug': [],
            'info': [],
            'warn': [],
            'error': [],
            'exception': [],
        }

    def debug(self, message):
        self.messages['debug'].append(message)

    def info(self, message):
        self.messages['info'].append(message)

    def warn(self, message):
        self.messages['warn'].append(message)

    def error(self, message):
        self.messages['error'].append(message)

    def exception(self, message):
        self.messages['exception'].append(message)

    def string_appears_in(self, level, search_string):
        """
            Check for a specific string appearing in at least one message of
            the specified level.
            If a tuple or list is supplied, all elements must be present in
            a single message of the specified level.
        """
        if isinstance(search_string, text_type):
            search_string = [search_string]
        for message in self.messages[level]:
            if all(search in message.lower()
                   for search in search_string):
                return True
        # This is probably about to lead to an assertion error, leave some
        # useful output
        print('{level} log messages: {messages}'.format(
            level=level.capitalize(),
            messages=self.messages[level],
        ))
        print('All logs:')
        pprint(self.messages)
        return False


class FakeStdin(object):
    def __init__(self, lines):
        self._lines = lines

    def readline(self):
        return self._lines.pop(0)

    def readlines(self):
        lines = self._lines
        self._lines = []
        return lines


class FakeOidLookup(object):
    def __init__(self, lookups=None, default=None):
        self.lookups = lookups or {}
        self.default = default

    def get(self, key):
        if isinstance(key, text_type):
            if key in self.lookups:
                return self.lookups[key]
            else:
                return self.default
        else:
            results = []
            for k in key:
                results.append(self.get(k))
            return results


class FakeOpener(object):
    def __init__(self, read_return=None,
                 write_error=None,
                 read_error=None):
        self.read_paths = []
        self.write_paths = []
        self.read_return = read_return
        self.write_error = write_error
        self.read_error = read_error

    @contextmanager
    def open(self, path, mode='r'):
        if mode == 'w':
            self.write_paths.append(path)
            if self.write_error:
                raise self.write_error
        else:
            self.read_paths.append(path)
            if self.read_error:
                raise self.read_error

        yield self

    def read(self):
        return self.read_return

    def write(self, *args):
        pass
