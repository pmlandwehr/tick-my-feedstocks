## tick-feedstocks

This is a program designed to help keep any [conda-forge](https://conda-forge.github.io/) feedstocks that you administer up to do date. It's *not* a polished, up-to-date package. It's a supplement to help folks eyeball their packages more easily, not a replacement for checking all of your packages.

To use it:

```bash
python tick-feedstocks/core.py <password_or_oauth> [--user <user>]
```

On execution, the program will:
* Identify all of the feedstocks that the user maintains.
* Identify those that are behind their corresponding [pypi](https://pypi.python.org/pypi) versions.
* Filter this list for the subset that don't depend on any other out-of-date feedstocks.
* For each feedstock *f* in the remaining list:
    * Attempt to trivially patch *f* by updating its version number and hash checksum.
    * Rerender *f* using the latest version of [conda-smithy](https://github.com/conda-forge/conda-smithy) and commit the change.
    * Submit a pull request for *f* to the origin on conda-forge.


Recipes versioned in this manner **SHOULD BE DOUBLE-CHECKED**. Because we do limited testing of conda-forge packages, it's quite possible that after a version requirement has been changed upstream the CIs won't throw an error. So, before merging any bot-submitted pulls, please make sure that all of the requirements are still correct.


### OAuth Tokens

If you want to use an OAuthToken instead of you github password, you should make sure that the token has these permissions:
* `public_repo`
* `read:org`
* `delete_repo` (This is unnecessary if you have no out-of-date forks of your feedstocks)
