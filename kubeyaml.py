import sys
import argparse
import functools
import collections
import re
from ruamel.yaml import YAML

import yaml


class NotFound(Exception):
    pass


class UnresolvablePath(Exception):
    pass


# The container name, by proclamation, used for an image supplied in a
# FluxHelmRelease
# Only keeping as it's used by tests
FHR_CONTAINER = "chart-image"


def parse_args():
    p = argparse.ArgumentParser()
    subparsers = p.add_subparsers()

    image = subparsers.add_parser("image", help="update an image ref")
    image.add_argument("--namespace", required=True)
    image.add_argument("--kind", required=True)
    image.add_argument("--name", required=True)
    image.add_argument("--container", required=True)
    image.add_argument("--image", required=True)
    image.set_defaults(func=update_image)

    def keyValuePair(s):
        k, v = s.split("=")
        return k, v

    annotation = subparsers.add_parser("annotate", help="update annotations")
    annotation.add_argument("--namespace", required=True)
    annotation.add_argument("--kind", required=True)
    annotation.add_argument("--name", required=True)
    annotation.add_argument("notes", nargs="+", type=keyValuePair)
    annotation.set_defaults(func=update_annotations)

    set = subparsers.add_parser("set", help="update values by their dot notation paths")
    set.add_argument("--namespace", required=True)
    set.add_argument("--kind", required=True)
    set.add_argument("--name", required=True)
    set.add_argument("paths", nargs="+", type=keyValuePair)
    set.set_defaults(func=set_paths)

    return p.parse_args()


def bail(reason):
    sys.stderr.write(reason)
    sys.stderr.write("\n")
    sys.exit(2)


class AlwaysFalse(object):
    def __init__(self):
        pass

    def __get__(self, instance, owner):
        return False

    def __set__(self, instance, value):
        pass


def apply_to_yaml(fn, infile, outfile):
    docs = yaml.load_all(infile, Loader=yaml.CSafeLoader)
    yaml.dump_all(fn(docs), outfile, Dumper=yaml.CSafeDumper, explicit_start=True)


def update_image(args, docs):
    """Update the manifest specified by args, in the stream of docs"""
    found = False
    for doc in docs:
        if not found:
            for m in manifests(doc):
                c = find_container(args, m)
                if c != None:
                    set_container_image(m, c, args.image)
                    found = True
                    break
        yield doc
    if not found:
        raise NotFound()


def update_annotations(spec, docs):
    def ensure(d, *keys):
        for k in keys:
            try:
                d = d[k]
            except KeyError:
                d[k] = dict()
                d = d[k]
        return d

    found = False
    for doc in docs:
        if not found:
            for m in manifests(doc):
                if match_manifest(spec, m):
                    notes = ensure(m, "metadata", "annotations")
                    for k, v in spec.notes:
                        if v == "":
                            try:
                                del notes[k]
                            except KeyError:
                                pass
                        else:
                            notes[k] = v
                    if len(notes) == 0:
                        del m["metadata"]["annotations"]
                    found = True
                    break
        yield doc
    if not found:
        raise NotFound()


def set_paths(spec, docs):
    def set_path(d, path, value):
        keys = path.split(".")
        for k in keys[:-1]:
            if k not in d:
                return False
            d = d[k]
        if isinstance(d[keys[-1]], collections.Mapping):
            return False
        d[keys[-1]] = value
        return True

    found = False
    unresolvable = list()
    for doc in docs:
        if not found:
            for m in manifests(doc):
                if match_manifest(spec, m):
                    for k, v in spec.paths:
                        if not set_path(m, k, v):
                            unresolvable.append(k)
                    found = True
                    break
        yield doc
    if len(unresolvable):
        raise UnresolvablePath(unresolvable)
    if not found:
        raise NotFound()


def manifests(doc):
    if doc == None:
        return collections.OrderedDict()
    if doc["kind"].endswith("List"):
        for m in doc["items"]:
            yield m
    else:
        yield doc


def match_manifest(spec, manifest):
    try:
        # NB treat the Kind as case-insensitive
        if manifest["kind"].lower() != spec.kind.lower():
            return False
        if manifest["metadata"].get("namespace", "default") != spec.namespace:
            return False
        if manifest["metadata"]["name"] != spec.name:
            return False
    except KeyError:
        return False
    return True


def podspec(manifest):
    if manifest["kind"] == "CronJob":
        spec = manifest["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    else:
        spec = manifest["spec"]["template"]["spec"]
    return spec


def containers(manifest):
    spec = podspec(manifest)
    return spec.get("containers", []) + spec.get("initContainers", [])


def find_container(spec, manifest):
    if not match_manifest(spec, manifest):
        return None
    for c in containers(manifest):
        if c["name"] == spec.container:
            return c
    return None


def set_container_image(manifest, container, image):
    container["image"] = image


def mappings(values):
    return (
        (k, values[k]) for k in values if isinstance(values[k], collections.Mapping)
    )

    def set_image(values):
        image = values["image"]
        imageKey = "image"

        if isinstance(image, collections.Mapping) and "repository" in image:
            values = image
            imageKey = "repository"

        reg, im, tag = parse_ref()

        if "registry" in values and "tag" in values:
            values["registry"] = reg
            values[imageKey] = im
            values["tag"] = tag
        elif "registry" in values:
            values["registry"] = reg
            values[imageKey] = ":".join(filter(None, [im, tag]))
        elif "tag" in values:
            values[imageKey] = "/".join(filter(None, [reg, im]))
            values["tag"] = tag
        else:
            values[imageKey] = replace

    values = manifest["spec"]["values"]
    for k, v in mappings(values):
        if k == container["name"] and "image" in v:
            set_image(v)
            return
    raise NotFound


def main():
    args = parse_args()
    try:
        apply_to_yaml(functools.partial(args.func, args), sys.stdin, sys.stdout)
    except NotFound:
        bail("manifest not found")
    except UnresolvablePath as e:
        bail("unable to resolve path(s):\n" + "\n".join(e.args[0]))


if __name__ == "__main__":
    main()
