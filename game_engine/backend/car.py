import math

import numpy as np
import pygame

from game_engine.backend.geometry import calculateDistance, move, rotation, sigmoid
from game_engine.backend.settings import COLOR_LINE, MAX_SPEED, WHITE
from game_engine.backend.track import TrackGeometry

collision_surface = None
default_car_image = None
maxspeed = MAX_SPEED


def configure_car(collision_map, car_image, max_speed=MAX_SPEED):
    global collision_surface, default_car_image, maxspeed
    collision_surface = collision_map
    default_car_image = car_image
    maxspeed = max_speed


def set_collision_map(collision_map):
    global collision_surface
    collision_surface = collision_map


class Car:
  def __init__(self, sizes):
    self.score = 0
    self.fitness_score = 0.0
    self.num_layers = len(sizes)
    self.sizes = sizes
    self.biases = [np.random.randn(y, 1) for y in sizes[1:]]
    self.weights = [np.random.randn(y, x) for x, y in zip(sizes[:-1], sizes[1:])]
    self.c1 = 0,0
    self.c2 = 0,0
    self.c3 = 0,0
    self.c4 = 0,0
    self.c5 = 0,0
    self.d1 = 0
    self.d2 = 0
    self.d3 = 0
    self.d4 = 0
    self.d5 = 0
    self.yaReste = False
    self.inp = np.array([[self.d1],[self.d2],[self.d3],[self.d4],[self.d5]])
    self.outp = np.array([[0],[0],[0],[0]])
    self.showlines = False
    self.x = 120
    self.y = 480
    self.center = self.x, self.y
    self.height = 35
    self.width = 17
    self.d = self.x-(self.width/2),self.y-(self.height/2)
    self.c = self.x + self.width-(self.width/2), self.y-(self.height/2)
    self.b = self.x + self.width-(self.width/2), self.y + self.height-(self.height/2)
    self.a = self.x-(self.width/2), self.y + self.height-(self.height/2)
    self.velocity = 0
    self.acceleration = 0
    self.angle = 180
    self.collided = False
    self.color = WHITE
    self.car_image = default_car_image

  def set_accel(self, accel):
    self.acceleration = accel

  def rotate(self, rot):
    self.angle += rot
    if self.angle > 360:
        self.angle = 0
    if self.angle < 0:
        self.angle = 360 + self.angle

  def update(self, track: TrackGeometry | None = None):
    if self.acceleration != 0:
        self.velocity += self.acceleration
        if self.velocity > maxspeed:
            self.velocity = maxspeed
        elif self.velocity < 0:
            self.velocity = 0
    else:
        self.velocity *= 0.92

    self.x, self.y = move((self.x, self.y), self.angle, self.velocity)
    self.center = self.x, self.y

    self._update_corners()
    self._update_sensors(track)

  def _update_corners(self):
    self.d = self.x-(self.width/2),self.y-(self.height/2)
    self.c = self.x + self.width-(self.width/2), self.y-(self.height/2)
    self.b = self.x + self.width-(self.width/2), self.y + self.height-(self.height/2)
    self.a = self.x-(self.width/2), self.y + self.height-(self.height/2)

    self.a = rotation((self.x,self.y), self.a, math.radians(self.angle))
    self.b = rotation((self.x,self.y), self.b, math.radians(self.angle))
    self.c = rotation((self.x,self.y), self.c, math.radians(self.angle))
    self.d = rotation((self.x,self.y), self.d, math.radians(self.angle))

  def _surface_contains(self, point):
    if collision_surface is None:
        return False
    x, y = int(point[0]), int(point[1])
    width, height = collision_surface.get_size()
    return 0 <= x < width and 0 <= y < height and collision_surface.get_at((x, y)).a != 0

  def _sensor_endpoint(self, angle, contains, step):
    point = move((self.x, self.y), angle, 10)
    max_steps = 10000
    steps = 0
    while contains(point):
        point = move(point, angle, step)
        steps += 1
        if steps >= max_steps:
            raise RuntimeError("Sensor ray did not leave the track")
    return move(point, angle, -1)

  def _update_sensors(self, track: TrackGeometry | None):
    contains = track.contains if track is not None else self._surface_contains
    step = 4 if track is not None else 10
    angles = (
        self.angle,
        self.angle + 45,
        self.angle - 45,
        self.angle + 90,
        self.angle - 90,
    )
    endpoints = [
        self._sensor_endpoint(sensor_angle, contains, step)
        for sensor_angle in angles
    ]
    self.c1, self.c2, self.c3, self.c4, self.c5 = endpoints
    distances = [
        calculateDistance(self.center[0], self.center[1], point[0], point[1])
        for point in endpoints
    ]
    self.d1, self.d2, self.d3, self.d4, self.d5 = distances

  def refresh_track_state(self, track: TrackGeometry):
    self.center = self.x, self.y
    self._update_corners()
    self._update_sensors(track)

  def draw(self, display):
    rotated_image = pygame.transform.rotate(self.car_image, -self.angle-180)
    rect_rotated_image = rotated_image.get_rect()
    rect_rotated_image.center = self.x, self.y
    display.blit(rotated_image, rect_rotated_image)

    if self.showlines:
        pygame.draw.line(display, COLOR_LINE, (self.x,self.y), self.c1, 2)
        pygame.draw.line(display, COLOR_LINE, (self.x,self.y), self.c2, 2)
        pygame.draw.line(display, COLOR_LINE, (self.x,self.y), self.c3, 2)
        pygame.draw.line(display, COLOR_LINE, (self.x,self.y), self.c4, 2)
        pygame.draw.line(display, COLOR_LINE, (self.x,self.y), self.c5, 2)

  def showLines(self):
    self.showlines = not self.showlines

  def feedforward(self):
    self.inp = np.array([[self.d1],[self.d2],[self.d3],[self.d4],[self.d5],[self.velocity]])
    for b, w in zip(self.biases, self.weights):
        self.inp = sigmoid(np.dot(w, self.inp)+b)
    self.outp = self.inp
    return self.outp

  def collision(self, track: TrackGeometry | None = None):
      contains = track.contains if track is not None else self._surface_contains
      return not all(contains(corner) for corner in (self.a, self.b, self.c, self.d))

  def resetPosition(self):
      self.reset_state()

  def reset_state(self, x=120, y=480, angle=180, car_image=None):
      self.x = x
      self.y = y
      self.center = self.x, self.y
      self.velocity = 0
      self.acceleration = 0
      self.angle = angle
      self.collided = False
      self.yaReste = False
      self.score = 0
      self.fitness_score = 0.0
      self.d1 = 0
      self.d2 = 0
      self.d3 = 0
      self.d4 = 0
      self.d5 = 0
      self.inp = np.array([[self.d1],[self.d2],[self.d3],[self.d4],[self.d5]])
      self.outp = np.array([[0],[0],[0],[0]])
      self.d = self.x-(self.width/2),self.y-(self.height/2)
      self.c = self.x + self.width-(self.width/2), self.y-(self.height/2)
      self.b = self.x + self.width-(self.width/2), self.y + self.height-(self.height/2)
      self.a = self.x-(self.width/2), self.y + self.height-(self.height/2)
      self._update_corners()
      if car_image is not None:
          self.car_image = car_image

  def takeAction(self):
    if self.outp.item(0) > 0.5:
        self.set_accel(0.2)
    else:
        self.set_accel(0)
    if self.outp.item(1) > 0.5:
        self.set_accel(-0.2)
    if self.outp.item(2) > 0.5:
        self.rotate(-5)
    if self.outp.item(3) > 0.5:
        self.rotate(5)
