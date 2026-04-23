#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 11:56:00 2026

@author: imchugh
"""

render_editor_callback = None

def set_render_callback(fn):
    global render_editor_callback
    render_editor_callback = fn


def trigger_render():
    if render_editor_callback:
        render_editor_callback()