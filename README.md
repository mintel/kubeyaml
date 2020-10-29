# kubeyaml
Small program for updating kube yamels in-place

This is a fork of https://github.com/squaremo/kubeyaml/ and uses `py-yaml` C bindings for
improved perf. 

See github.com/squaremo/kubeyaml/issues/17

---

This will eventually go away (based on decisions around kustomize/flux-v2) 

## Notable changes

- Use `CLoader` ( https://pyyaml.org/wiki/PyYAMLDocumentation )
    - Some differences in quoting / escaping
- Drop support for Helm (we don't use it)
- Switch to GithubActions