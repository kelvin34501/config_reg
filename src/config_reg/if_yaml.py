import yaml


def load_yaml(filename):
    with open(filename, "r") as f:
        res = yaml.safe_load(f)
    return res


def save_yaml(res, filename):
    with open(filename, "w") as f:
        yaml.dump(res, f)
