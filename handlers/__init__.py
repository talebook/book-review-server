#!/usr/bin/python
# -*- coding: UTF-8 -*-


def routes():
    from . import user
    from . import review
    from . import stat

    routes = []
    routes += user.routes()
    routes += review.routes()
    routes += stat.routes()
    return routes
