import re


def get_word_between(target, front_regex, back_regex):
    '''Return word between front regex and back regex in target
    if it is muliple, return only first
    if there is not, return empty string

    :param target: target string
    :param front_regex: regular expression
    :param back_regex: regular expression
    '''
    front_pattern = re.compile(front_regex)
    front_match = front_pattern.search(target)
    back_pattern = re.compile(back_regex)
    back_match = back_pattern.search(target)
    if not front_match or not back_match:
        return ''
    return str(target[front_match.end():back_match.start()])
