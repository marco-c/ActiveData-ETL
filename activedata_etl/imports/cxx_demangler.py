# encoding: utf-8
#
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http:# mozilla.org/MPL/2.0/.
#
# Author: Kyle Lahnakoski (kyle@lahnakoski.com)
#
from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from pyLibrary.debugs.logs import Log


def demangle(mangled_name):
    """
    RETURN signature ONLY IF IT CAN NOT BE DECODED
    :param mangled_name:
    :return: (name, params, signature) pair
    """
    if not mangled_name.startswith("_ZN"):
        Log.error("Do not know how to handle {{mangled_name}}", mangled_name=mangled_name)
    start = 3
    prefix = ""
    try:
        while mangled_name[start] in MODIFIERS:
            prefix = prefix + MODIFIERS[mangled_name[start]] + " "
            start += 1

        parts = split(mangled_name[start:])
        sig = parts[-1]
        params = demangle_sig(sig, parts[0])
    except Exception, e:
        params = None
        Log.warning("can not demangle {{mangled_name}}", mangled_name=mangled_name, cause=e)

    return prefix + "::".join(parts[:-1]), params, sig


# _ZN7mozilla19AnimValuesStyleRule8AddValueE15nsCSSPropertyIDRKNS
# void AnimValuesStyleRule::AddValue(nsCSSPropertyID aProperty, const StyleAnimationValue &aValue)
# _ZN7mozilla19AnimValuesStyleRule14QueryInterfaceERK4nsIDPPv
# mozilla::AnimValuesStyleRule::QueryInterface(nsID const&, void**)

def demangle_sig(sig, namespace):
    if sig == "v":
        return "()"

    i = 0
    output = ["("]
    modifiers = ""
    prefix = ""
    while i < len(sig):
        c = sig[i]
        m = MODIFIERS.get(c)
        if m:
            modifiers = m + modifiers
            i += 1
        elif c in TYPES:
            output.append(TYPES[c] + " " + modifiers)
            modifiers = ""
            i += 1
        elif c == 'N' and sig[i:i + 3] == "NS_":
            prefix = namespace + "::"
            i += 3
        elif c in "123456789":
            length = 0
            while c in "0123456789":
                length = length * 10 + (ord(c) - 48)
                i += 1
                c = sig[i]
            output.append(prefix + sig[i:length + i] + " " + modifiers)
            modifiers = ""
            i += length
        else:
            Log.error("Can not recognize type {{type|quote}}", type=c)
    output.append(")")
    return "".join(output)


MODIFIERS = {
    "P": "*",
    "K": "const",
    "R": "&",
    "O": "&&"
}

TYPES = {
    "v": "void",
    "E": ""
}


def split(mangled_name):
    output = []
    i = 0
    while i < len(mangled_name):
        length = 0
        c = mangled_name[i]
        if c == 'E':
            output.append(mangled_name[i + 1:])
            return output

        while c in "0123456789":
            length = length * 10 + (ord(c) - 48)
            i += 1
            c = mangled_name[i]
        if length == 0:
            Log.error("Expecting name to end with 'E'")
            output.append(mangled_name[i:])
            return output
        output.append(mangled_name[i: i + length])
        i += length
