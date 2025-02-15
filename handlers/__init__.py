#!/usr/bin/python
# -*- coding: UTF-8 -*-


def routes():
    from . import user
    from . import review

    routes = []
    routes += user.routes()
    routes += review.routes()
    return routes
