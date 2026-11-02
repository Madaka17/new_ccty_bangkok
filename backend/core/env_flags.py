"""On/off environment flags that default to on, such as YOLO_ALLOWED and BMA_FETCH."""

OFF_WORDS = {"0", "false", "no", "off"}


def flag_on(env, name):
    """True unless env[name] is 0 / false / no / off (any case, spaces ignored). Unset means on."""
    value = env.get(name)
    return value is None or value.strip().lower() not in OFF_WORDS
