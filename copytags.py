#!/usr/bin/python

import os, sys, re, UserDict
from warnings import warn
from itertools import *
import quodlibet.config
quodlibet.config.init()
from quodlibet.formats import MusicFile

# config.init(os.path.join(os.getenv("HOME") + ".quodlibet" + "config"))

class AudioFile(UserDict.DictMixin):
    """A simple class just for tag editing.

    No internal mutagen tags are exposed, or filenames or anything. So
    calling clear() won't destroy the filename field or things like
    that. Use it like a dict, then .write() it to commit the changes.

    Optional argument blacklist is a list of regexps matching
    non-transferrable tags. They will effectively be hidden, nether
    settable nor gettable.

    Or grab the actual underlying quodlibet format object from the
    .data field and get your hands dirty."""
    def __init__(self, filename, blacklist=()):
        self.data = MusicFile(filename)
        # Also exclude mutagen's internal tags
        self.blacklist = [ re.compile("^~") ] + blacklist
    def __getitem__(self, item):
        if self.blacklisted(item):
            warn("%s is a blacklisted key." % item)
        else:
            return self.data.__getitem__(item)
    def __setitem__(self, item, value):
        if self.blacklisted(item):
            warn("%s is a blacklisted key." % item)
        else:
            return self.data.__setitem__(item, value)
    def __delitem__(self, item):
        if self.blacklisted(item):
            warn("%s is a blacklisted key." % item)
        else:
            return self.data.__delitem__(item)
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
        return self.data.write()

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
    for a,b in izip(old_components, stripped_components):
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
        return os.path.join(target_dir, ifilter(filter_fun, files).next())
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
        return(list(set(items)))
    else:
        return(dict([(key_fun(i), i) for i in items]).values())

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
    return sorted(unique(music_files, key_fun=lambda x: x['~filename']))

def find_source_file(dest_file, src, dest):
    prefix_subbed = substitute_prefix(dest_file, dest, src)
    noext = os.path.splitext(prefix_subbed)[0]
    source_file = find_file_any_ext(noext)
    return source_file
    # return find_file_any_ext(substitute_prefix(os.path.splitext(dest_file)[0],dest,src))

def find_file_pairs(src,dest):
    """Returns a list of file pairs, each suitable for passing into copy_tags."""
    dest_files = map(lambda f: f['~filename'], get_all_music_files(dest))
    source_files = map(lambda f: find_source_file(f, src, dest), dest_files)
    return izip(source_files, dest_files)

def copy_tags_recursive(srcdir,destdir):
    srcdir = os.path.realpath(srcdir)
    destdir = os.path.realpath(destdir)
    for pair in find_file_pairs(srcdir,destdir):
        print """Copying from '%s' to '%s'""" % pair
        copy_tags(*pair)

def copy_tags (src, dest):
    m_src = AudioFile(src, blacklist = blacklist_regexes)
    m_dest = AudioFile(dest, blacklist = m_src.blacklist)
    m_dest.clear()
    m_dest.update(m_src)
    m_dest.write()

if __name__ == '__main__':
    if len(sys.argv[1:]) == 0:
        print "No files specified."
    if len(sys.argv[1:]) % 2 != 0:
        print "Need an even number of files."
    file_pairs = dict(zip(sys.argv[1::2],sys.argv[2::2]))
    for pair in file_pairs.iteritems():
        pair = tuple(map(os.path.realpath, pair))
        print """Copying tags from '%s' to '%s' """ % pair
        copy_tags_recursive(pair[0],pair[1])
