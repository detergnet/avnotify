#!/usr/bin/env python

# Copyright (c) 2014-2015, Marius Barbu <msb@avengis.com>
# All rights reserved.
#
# Released under BSD 2-Clause. See LICENSE for more information.

from __future__ import print_function
import sys
import os
import time
import errno
import subprocess
import re
import dbus

DBUS_NOTIF_PATH = "/org/freedesktop/Notifications"
DBUS_NOTIF_OBJECT = "org.freedesktop.Notifications"
DBUS_NOTIF_IFACE = "org.freedesktop.Notifications"

ICON_BASE_PLAYBACK = "audio-volume"
ICON_BASE_MICROPHONE = "microphone-sensitivity"
ICON_SUFFIXES = ["muted", "low", "medium", "high"]
TITLE_MICROPHONE = "Microphone"
TITLE_PLAYBACK = "Playback"
APP_NAME = "Alsa Volume Notifier"
APP_CACHE_NAME = "avnotify"
CACHE_TIMEOUT = 10


def send_notification(id, title, text, icon, hints=''):
    bus = dbus.SessionBus()
    obj = bus.get_object(DBUS_NOTIF_OBJECT, DBUS_NOTIF_PATH)
    notify = dbus.Interface(obj, DBUS_NOTIF_IFACE)
    return notify.Notify(APP_NAME, id, icon, title, text, '', hints, -1)


def ensure_path(path):
    """Create a path but don't throw an error if it already exists.
    All other errors are raised (EACCES, etc).
    """
    try:
        os.makedirs(path)
    except os.error as e:
        if e.errno != errno.EEXIST:
            raise


def as_float_default(s, default=0):
    """Cast a string to float or return a default value instead of throwing an
    error on invalid argument.
    """
    try:
        return float(s)
    except ValueError:
        return default


def xdg_cache_root():
    """Returns the cache folder according to the freedesktop XDG specification.
    """
    return os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))


def xdg_save_cache(app_name, key, value):
    """Save a (key, value) pair in the XDG cache location under a custom
    application name.
    """
    path = os.path.join(xdg_cache_root(), app_name, key)
    ensure_path(os.path.dirname(path))
    with open(path, "wt") as outf:
        print(time.time(), file=outf)
        print(value, file=outf)


def xdg_read_cache(app_name, key, timeout=None):
    """Read a value from the application's XDG cache, no older than timeout
    seconds.

    Returns None if the requested key is not found or the timeout
    has passed since the key was saved.
    """
    path = os.path.join(xdg_cache_root(), app_name, key)
    try:
        with open(path, "rt") as inf:
            tstamp = as_float_default(inf.readline().strip())
            if timeout and tstamp + timeout < time.time():
                return None
            return inf.read()
    except IOError:
        return None


def adjust_volume_alsa(args):
    """Adjust audio volume using ALSA according to ``args``.

    ``args`` can be anything that is accepted by the ``amixer set ...```
    command.

    Returns a tuple (is_microphone, volume_percent, is_muted) representing the
    final state of the audio device after executing the command.
    """
    level, muted, mic = 0, False, False
    pattern = re.compile("\[(\d+)%\].+?\[(on|off)\]")
    proc = subprocess.Popen(["amixer", "set"] + args, stdout=subprocess.PIPE)
    for line in proc.stdout:
        line = line.decode()
        if "cvolume" in line.split():
            mic = True
        match = pattern.search(line)
        if match:
            level = int(match.group(1))
            muted = match.group(2) == "off"
    if proc.wait() != 0:
        raise os.error(errno.EINVAL, os.strerror(errno.EINVAL), args)

    return mic, level, muted


def main(args):
    mic, level, muted = adjust_volume_alsa(args)
    level_index = 1 + min(100, level) // 34
    base = ICON_BASE_MICROPHONE if mic else ICON_BASE_PLAYBACK
    suffix = ICON_SUFFIXES[0] if muted else ICON_SUFFIXES[level_index]

    title = TITLE_MICROPHONE if mic else TITLE_PLAYBACK
    icon = "%s-%s" % (base, suffix)
    text = "Volume at %d%%%s" % (level, " (muted)" if muted else "")
    old_id = xdg_read_cache(APP_CACHE_NAME, "previous-id", CACHE_TIMEOUT) or "0"
    old_id = int(old_id.strip())
    new_id = send_notification(old_id, title, text, icon, dict(value=level))
    xdg_save_cache(APP_CACHE_NAME, "previous-id", new_id)

if __name__ == "__main__":
    main(sys.argv[1:])
