def set_value(config, key, value):
    key_list = key.split(".")
    handle = config
    for keypart in key_list[:-1]:
        handle = handle[keypart]
    handle[key_list[-1]] = value


def index_key(tree, key):
    if tree is None:
        return False, None

    key_list = key.split(".")
    handle = tree
    for keypart in key_list:
        if keypart not in handle:
            return False, None
        handle = handle[keypart]
    return True, handle


def del_value(config, key):
    key_list = key.split(".")
    handle = config
    traceback = []
    for keypart in key_list[:-1]:
        traceback.append(handle)
        handle = handle[keypart]
    if key_list[-1] in handle:
        del handle[key_list[-1]]
    
    # cleanup empty
    if len(key_list) > 1:
        for off, keypart in zip(range(len(key_list) - 2, -1, -1), key_list[-2::-1]):
            handle_curr = traceback[off]
            if len(handle_curr[keypart]) == 0:
                del handle_curr[keypart]