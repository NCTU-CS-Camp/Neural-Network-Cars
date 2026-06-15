import math

import numpy as np


def calculateDistance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def rotation(origin, point, angle):
    ox, oy = origin
    px, py = point

    qx = ox + math.cos(angle) * (px - ox) - math.sin(angle) * (py - oy)
    qy = oy + math.sin(angle) * (px - ox) + math.cos(angle) * (py - oy)
    return qx, qy


def move(point, angle, unit):
    x = point[0]
    y = point[1]
    rad = math.radians(-angle % 360)

    x += unit * math.sin(rad)
    y += unit * math.cos(rad)

    return x, y


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))
