import yaml


def load_yaml(filename):
    with open(filename, "r") as f:
        res = yaml.safe_load(f)
    return res
