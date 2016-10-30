#!/usr/bin/env python

import os, sys, re
import logging
# from itertools import *
from mutagen import File as MusicFile
from mutagen.aac import AACError
from six.moves import map

try:
    # Python 3
    from collections.abc import MutableMapping
except ImportError:
    # Python 2
    from UserDict import DictMixin as MutableMapping

# Set up logging
logFormatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.handlers = []
logger.addHandler(logging.StreamHandler())
for handler in logger.handlers:
    handler.setFormatter(logFormatter)

class AudioFile(MutableMapping):
    """A simple class just for tag editing.

    No internal mutagen tags are exposed, or filenames or anything. So
    calling clear() won't destroy the filename field or things like
    that. Use it like a dict, then .write() it to commit the changes.
    When saving, tags that cannot be saved by the file format will be
    skipped with a debug message, since this is a common occurrance
    with MP3/M4A.

    Optional argument blacklist is a list of regexps matching
    non-transferrable tags. They will effectively be hidden, nether
    settable nor gettable.

    Or grab the actual underlying mutagen format object from the
    .data field and get your hands dirty.

    """
    def __init__(self, filename, blacklist=[], easy=True):
        self.filename = filename
        self.data = MusicFile(self.filename, easy=easy)
        if self.data is None:
            raise ValueError("Unable to identify %s as a music file" % (repr(filename)))
        # Also exclude mutagen's internal tags
        self.blacklist = [ re.compile("^~") ] + blacklist
    def __getitem__(self, item):
        if self.blacklisted(item):
            logger.debug("Attempted to get blacklisted key: %s." % repr(item))
        else:
            return self.data.__getitem__(item)
    def __setitem__(self, item, value):
        if self.blacklisted(item):
            logger.debug("Attempted to set blacklisted key: %s." % repr(item))
        else:
            try:
                return self.data.__setitem__(item, value)
            except KeyError:
                logger.debug("Skipping unsupported tag %s for file type %s",
                             item, type(self.data))
    def __delitem__(self, item):
        if self.blacklisted(item):
            logger.debug("Attempted to del blacklisted key: %s." % repr(item))
        else:
            return self.data.__delitem__(item)
    def __len__(self):
        return len(self.keys())
    def __iter__(self):
        return iter(self.keys())

    def blacklisted(self, item):
        """Return True if tag is blacklisted.

        Blacklist automatically includes internal mutagen tags (those
        beginning with a tilde)."""
        for regex in self.blacklist:
            if re.search(regex, item):
                return True
        else:
            return False
    def keys(self):
        return [ key for key in self.data.keys() if not self.blacklisted(key) ]
    def write(self):
        return self.data.save()

# A list of regexps matching non-transferrable tags, like file format
# info and replaygain info. This will not be transferred from source,
# nor deleted from destination.
blacklist_regexes = [ re.compile(s) for s in (
        'encoded',
        'replaygain',
        ) ]

def substitute_prefix(path, oldprefix, newprefix):
    """Given a path that starts with oldprefix, strip that prefix and
    replace it with newprefix."""
    path_components = os.path.normpath(path).split(os.sep)
    old_components = os.path.normpath(oldprefix).split(os.sep)
    new_components = os.path.normpath(newprefix).split(os.sep)
    stripped_components = path_components[:len(old_components)]
    # Check to make sure path starts with oldprefix
    for a,b in zip(old_components, stripped_components):
        if a != b:
            raise Exception("path '%s' does not start with oldprefix '%s'" % (path, oldprefix))
    unstripped_components = path_components[len(old_components):]
    full_path = new_components + unstripped_components
    # Absolute path ends up with an empty string at the front, which
    # must be changed to a slash
    if full_path[0] == '':
        full_path[0] = '/'
    return os.path.join(*full_path)

def find_file_any_ext(path):
    """Given a path, returns the path of an existing file with that
    path and possibly an extension.

    For example, for '/usr/share/test', it would find
    '/usr/share/text.txt'."""
    target_base = os.path.basename(path)
    target_dir = os.path.dirname(path)
    files = sorted(os.listdir(target_dir))
    def filter_fun(p):
        base = os.path.splitext(p)[0]
        return base == target_base
    try:
        return os.path.join(target_dir, next(iter(filter(filter_fun, files))))
    except StopIteration:
        raise Exception("Could not find a file with a basename of %s" % (path, ))

def remove_hidden_paths(paths):
    '''Remove UNIX-style hidden paths from a list.'''
    return [ p for p in paths if not re.search('^\.',p)]

def unique (items, key_fun = None):
    '''Return an unique list of items, where two items are considered
    non-unique if key_fun returns the same value for both of them.

    If no key_fun is provided, then the identity function is assumed,
    in which case this is equivalent to list(set(items)).'''
    if key_fun is None:
        return list(set(items))
    else:
        return list({ key_fun(i): i for i in items }.values())

def get_all_music_files (paths, ignore_hidden=True):
    '''Recursively search in one or more paths for music files.

    By default, hidden files and directories are ignored.'''
    music_files = []
    if isinstance(paths, str):
        paths = (paths, )
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p, followlinks=True):
                if ignore_hidden:
                    files = remove_hidden_paths(files)
                    dirs = remove_hidden_paths(dirs)
                # Try to load every file as an audio file, and filter the
                # ones that aren't actually audio files
                more_files = [ MusicFile(os.path.join(root, x)) for x in files ]
                music_files.extend([ f for f in more_files if f is not None ])
        else:
            f = MusicFile(p)
            if f is not None:
                music_files.append(f)

    # Filter duplicate files and return
    return sorted(unique(music_files, key_fun=lambda x: x.filename))

def find_source_file(dest_file, src, dest):
    prefix_subbed = substitute_prefix(dest_file, dest, src)
    noext = os.path.splitext(prefix_subbed)[0]
    source_file = find_file_any_ext(noext)
    return source_file

def find_file_pairs(src,dest):
    """Returns a list of file pairs, each suitable for passing into copy_tags."""
    dest_files = map(lambda f: f.filename, get_all_music_files(dest))
    # source_files = map(lambda f: find_source_file(f, src, dest), dest_files)
    return ((find_source_file(destfile, src, dest), destfile)
            for destfile in dest_files)

def copy_tags_recursive(srcdir,destdir):
    srcdir = os.path.realpath(srcdir)
    destdir = os.path.realpath(destdir)
    for pair in find_file_pairs(srcdir,destdir):
        logger.info("""Copying tags from '%s' to '%s'""" % pair)
        copy_tags(*pair)

def copy_tags (src, dest):
    """Replace tags of dest file with those of src.

Excludes format-specific tags and replaygain info, which does not
carry across formats."""
    try:
        m_src = AudioFile(src, blacklist = blacklist_regexes, easy=True)
        m_dest = AudioFile(dest, blacklist = m_src.blacklist, easy=True)
        m_dest.clear()
        logger.debug("Adding tags from source file:\n%s",
                      "\n".join("%s: %s" % (k, repr(m_src[k])) for k in sorted(m_src.keys())))
        m_dest.update(m_src)
        logger.debug("Added tags to dest file:\n%s",
                     "\n".join("%s: %s" % (k, repr(m_dest[k])) for k in sorted(m_dest.keys())))
        m_dest.write()
    except AACError:
        logger.warn("No tags copied because output format does not support tags: %s", repr(type(m_dest.data)))

if __name__ == '__main__':
    if len(sys.argv[1:]) == 0:
        logger.error("No files specified.")
        sys.exit(1)
    if len(sys.argv[1:]) % 2 != 0:
        logger.error("Need an even number of files.")
        sys.exit(2)
    file_pairs = dict(zip(sys.argv[1::2],sys.argv[2::2]))
    for pair in file_pairs.items():
        pair = tuple(map(os.path.realpath, pair))
        copy_tags_recursive(pair[0],pair[1])
