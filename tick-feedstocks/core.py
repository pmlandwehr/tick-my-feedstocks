import argparse
from base64 import b64encode
from collections import namedtuple
from bs4 import BeautifulSoup
from github import Github
from github import GithubException
from jinja2 import Template
from jinja2 import UndefinedError
from pkg_resources import parse_version
import re
import requests
import subprocess
from tqdm import tqdm
import yaml


pypi_pkg_uri = 'https://pypi.python.org/pypi/{}/json'.format

fs_tuple = namedtuple('fs_status', 'success '
                                   'needs_update '
                                   'data')

status_data_tuple = namedtuple('status_data', 'text '
                                              'yaml_strs '
                                              'pypi_version '
                                              'reqs '
                                              'blob_sha')


def pypi_org_sha(package_name, version, bundle_type):
    """
    Scrape pypi.org for SHA256 of the source bundle
    :param str package_name: Name of package (PROPER case)
    :param str version: version for which to get sha
    :param str bundle_type: ".tar.gz", ".zip" - format of bundle
    :returns: `str` -- SHA256 for a source bundle
    """
    r = requests.get('https://pypi.org/project/{}/{}/#files'.format(
        package_name,
        version))

    bs = BeautifulSoup(r.text, 'html5lib')
    try:
        sha_val = bs.find('a',
                          {'href':
                           re.compile('https://files.pythonhosted.org.*{}-{}{}'.
                                      format(package_name,
                                             version,
                                             bundle_type))
                           }).next.next.next['data-clipboard-text']
    except AttributeError:
        # Bad parsing of page, couldn't get SHA256
        return None

    return sha_val


def pypi_version_str(package_name):
    """
    Retrive the latest version of a package in pypi
    :param str package_name:
    :return: `str` -- Version string
    """
    r = requests.get(pypi_pkg_uri(package_name))
    if not r.ok:
        return False
    return r.json()['info']['version'].strip()


def parsed_meta_yaml(text):
    """
    :param str text: The raw text in conda-forge feedstock meta.yaml file
    :return: `dict|None` -- parsed YAML dict if successful, None if not
    """
    try:
        yaml_dict = yaml.load(Template(text).render())
    except UndefinedError:
        # assume we hit a RECIPE_DIR reference in the vars and can't parse it.
        # just erase for now
        try:
            yaml_dict = yaml.load(
                Template(
                    re.sub('{{ (environ\[")?RECIPE_DIR("])? }}/', '',
                           text)
                ).render())
        except:
            return None
    except:
        return None

    return yaml_dict


def basic_patch(text, yaml_strs, pypi_version, blob_sha):
    """
    Given a meta.yaml file, version strings, and appropriate hashes,
    find and replace old versions and hashes, and create a patch.
    :param str text: The raw text
    :param dict yaml_strs:
    :param str pypi_version:
    :param str blob_sha:
    :return: `tpl(bool,str|dict)` -- True if success and commit dict for github, false and error otherwise
    """
    pypi_sha = pypi_org_sha(
        '-'.join(yaml_strs['source_fn'].split('-')[:-1]),
        pypi_version,
        yaml_strs['source_fn'].split(yaml_strs['version'])[-1]
    )

    if pypi_sha is None:
        return False, 'Couldn\'t get SHA from PyPI'

    if text.find(yaml_strs['version']) < 0 or text.find(yaml_strs['sha256']) < 0:
        # if we can't change both the version and the hash
        # do nothing
        return False, 'Couldn\'t find current version or SHA in meta.yaml'

    new_text = text.replace(yaml_strs['version'], pypi_version).\
        replace(yaml_strs['source']['sha256'], pypi_sha)

    commit_dict = {
        'message': 'Tick version to {}'.format(pypi_version),
        'content': b64encode(new_text.encode('utf-8')).decode('utf-8'),
        'sha': blob_sha
    }

    return True, commit_dict


def user_feedstocks(user):
    """
    :param github.AuthenticatedUser.AutheticatedUser user:
    :return: `list` -- list of conda-forge feedstocks the user maintains
    """
    feedstocks = []
    for team in tqdm(user.get_teams()):

        # Each conda-forge team manages one feedstock
        # If a team has more than one repo, skip it.
        if team.repos_count != 1:
            continue

        repo = list(team.get_repos())[0]
        if repo.full_name[:12] == 'conda-forge/' and repo.full_name[-10:] == '-feedstock':
            feedstocks.append(repo)

    return feedstocks


def feedstock_status(feedstock):
    """
    Return whether or not a feedstock is out of date and any information needed to update it.
    :param github.Repository.Repository feedstock:
    :return: `tpl(bool,bool,obj)` -- bools indicating success and either None or a tuple of data
    """

    meta_yaml = feedstock.get_contents('recipe/meta.yaml')

    yaml_dict = parsed_meta_yaml(meta_yaml.decoded_content)
    if yaml_dict is None:
        return fs_tuple(False, False, 'Couldn\'t parse meta.yaml')

    yaml_strs = dict()
    for x, y in [('version', ('package', 'version')),
                 ('source_fn', ('source', 'fn')),
                 ('sha256', ('source', 'sha256'))]:
        try:
            yaml_strs[x] = str(yaml_dict[y[0], y[1]]).strip()
        except KeyError:
            return fs_tuple(False, False, 'Missing meta.yaml key: [{}][{}]'.format(y[0], y[1]))

    pypi_version = pypi_version_str(feedstock.full_name[12:-10])
    if pypi_version is False:
        return fs_tuple(False, False, 'Couldn\'t find package in PyPI')

    if parse_version(yaml_strs['version']) >= parse_version(pypi_version):
        return fs_tuple(True, False, None)

    reqs = set()
    for step in yaml_dict['requirements']:
        reqs.update({x.split()[0] for x in yaml_dict['requirements'][step]})

    return fs_tuple(True,
                    True,
                    status_data_tuple(meta_yaml.decoded_content,
                                      yaml_strs,
                                      pypi_version,
                                      reqs - {'python', 'setuptools'},
                                      meta_yaml.sha))


def get_user_fork(user, feedstock):
    """
    Return a user's fork of a feedstock if one exists, else create a new one.
    :param github.AuthenticatedUser.AuthenticatedUser user:
    :param github.Repository.Repository feedstock:
    :return: `github.Repository.Repository` -- fork of the feedstock beloging to user
    """
    for fork in feedstock.get_forks():
        if fork.owner.login == user.login:
            return fork

    return user.create_fork(feedstock)


def even_feedstock_fork(user, feedstock):
    """
    Return a fork that's even with the latest version of the feedstock
    If the user has a fork that's ahead of the feedstock, do nothing
    :param github.AuthenticatedUser.AuthenticatedUser user: GitHub user
    :param github.Repository.Repository feedstock: conda-forge feedstock
    :return: `None|github.Repository.Repository` -- None if no fork, else the repository
    """
    fork = get_user_fork(user, feedstock)

    comparison = fork.compare(base='{}:master'.format(user.login),
                              head='conda-forge:master')

    if comparison.ahead_by > 0:
        # fork is *ahead* of master
        # leave everything alone - don't want to mess.
        return None
    elif comparison.behind_by > 0:
        # fork is *behind* master
        # delete fork and clone from scratch
        try:
            fork.delete()
        except GithubException:
            # couldn't delete feedstock
            # give up, don't want a mess.
            return None

        fork = user.create_fork(feedstock)

    return fork


def tick_feedstocks(gh_password, gh_user=None):
    """
    Finds all of the feedstocks a user maintains that can be updated without
    a dependency conflict with other feedstocks the user maintains,
    creates forks, ticks versions and hashes, and rerenders,
    then submits a pull
    :param str gh_password: GitHub password or OAuth token
    :param str gh_user: GitHub username (can be omitted with OAuth)
    """

    if gh_user is None:
        g = Github(gh_password)
        user = g.get_user()
        gh_user = user.login
    else:
        g = Github(gh_user, gh_password)
        user = g.get_user()

    feedstocks = user_feedstocks(user)
    statuses = [feedstock_status(feedstock)
                for feedstock in tqdm(feedstocks)]

    can_be_updated = []
    cannot_be_updated = []
    for fs, status in zip(feedstocks, statuses):
        if status.success and status.needs_update:
            can_be_updated.append((fs, status))
        else:
            cannot_be_updated.append((fs.full_name, status.data))

    package_names = set([x[0].full_name[12:-10] for x in can_be_updated])

    indep_updates = [x for x in can_be_updated
                     if len(x[1].data.reqs & package_names) < 1]

    successful_forks = []
    successful_updates = []
    failed_updates = []
    for update in tqdm(indep_updates):
        # generate basic patch
        patch = basic_patch(update[1].data.text,
                            update[1].data.yaml_strs,
                            update[1].data.pypi_version,
                            update[1].data.blob_sha)

        if patch[0] is False:
            # couldn't apply patch
            failed_updates.append(update)
            continue

        # make fork
        fork = even_feedstock_fork(user, update[0])

        if fork is None:
            # forking failed
            failed_updates.append(update)
            continue

        # patch fork
        r = requests.put(
            'https://api.github.com/{}/contents/recipe/meta.yaml'.format(
                fork.full_name),
            json=patch[1],
            auth=(user.login, gh_password))

        if not r.ok:
            # something broke.
            failed_updates.append(update)
            continue

        successful_updates.append(update)
        successful_forks.append(fork)

    subprocess.run(['conda', 'update', '-y', 'conda-smithy'])
    for fork in tqdm(successful_forks):
        subprocess.run(["./renderer.sh",
                        gh_user,
                        gh_password,
                        fork.full_name[12:]])

    # Log updates that couldn't be performed
    print('Couldn\'t update:')
    for tpl in cannot_be_updated:
        print('  {}: {}'.format(tpl[0], tpl[1]))

    # Log updates that failed
    print('Failed to update:')
    for update in failed_updates:
        print(' {}'.format(update[0].full_name))


def main():
    """
    Get user ID and authorization from input, then tick their feedstocks
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('password_or_oauth',
                        dest='password',
                        help='GitHub password or oauth token')
    parser.add_argument('--user',
                        dest='user',
                        help='GitHub username')
    args = parser.parse_args()

    if 'user' in args:
        tick_feedstocks(args['password'], args['user'])
    else:
        tick_feedstocks(args['password'])


if __name__ == "__main__":
    main()
