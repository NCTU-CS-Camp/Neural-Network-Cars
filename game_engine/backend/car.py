import math

import numpy as np
import pygame

from game_engine.backend.geometry import calculateDistance, move, rotation, sigmoid
from game_engine.backend.settings import COLOR_LINE, MAX_SPEED, WHITE

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
    # Existing training code configures a global map. Replays can override it per car.
    self.collision_surface = collision_surface

  def set_accel(self, accel):
    self.acceleration = accel

  def rotate(self, rot):
    self.angle += rot
    if self.angle > 360:
        self.angle = 0
    if self.angle < 0:
        self.angle = 360 + self.angle

  def update(self):
    self.score += self.velocity
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

    self.d = self.x-(self.width/2),self.y-(self.height/2)
    self.c = self.x + self.width-(self.width/2), self.y-(self.height/2)
    self.b = self.x + self.width-(self.width/2), self.y + self.height-(self.height/2)
    self.a = self.x-(self.width/2), self.y + self.height-(self.height/2)

    self.a = rotation((self.x,self.y), self.a, math.radians(self.angle))
    self.b = rotation((self.x,self.y), self.b, math.radians(self.angle))
    self.c = rotation((self.x,self.y), self.c, math.radians(self.angle))
    self.d = rotation((self.x,self.y), self.d, math.radians(self.angle))

    bg4 = self.collision_surface or collision_surface
    self.c1 = move((self.x,self.y),self.angle,10)
    while bg4.get_at((int(self.c1[0]),int(self.c1[1]))).a!=0:
        self.c1 = move((self.c1[0],self.c1[1]),self.angle,10)
    while bg4.get_at((int(self.c1[0]),int(self.c1[1]))).a==0:
        self.c1 = move((self.c1[0],self.c1[1]),self.angle,-1)

    self.c2 = move((self.x,self.y),self.angle+45,10)
    while bg4.get_at((int(self.c2[0]),int(self.c2[1]))).a!=0:
        self.c2 = move((self.c2[0],self.c2[1]),self.angle+45,10)
    while bg4.get_at((int(self.c2[0]),int(self.c2[1]))).a==0:
        self.c2 = move((self.c2[0],self.c2[1]),self.angle+45,-1)

    self.c3 = move((self.x,self.y),self.angle-45,10)
    while bg4.get_at((int(self.c3[0]),int(self.c3[1]))).a!=0:
        self.c3 = move((self.c3[0],self.c3[1]),self.angle-45,10)
    while bg4.get_at((int(self.c3[0]),int(self.c3[1]))).a==0:
        self.c3 = move((self.c3[0],self.c3[1]),self.angle-45,-1)

    self.c4 = move((self.x,self.y),self.angle+90,10)
    while bg4.get_at((int(self.c4[0]),int(self.c4[1]))).a!=0:
        self.c4 = move((self.c4[0],self.c4[1]),self.angle+90,10)
    while bg4.get_at((int(self.c4[0]),int(self.c4[1]))).a==0:
        self.c4 = move((self.c4[0],self.c4[1]),self.angle+90,-1)

    self.c5 = move((self.x,self.y),self.angle-90,10)
    while bg4.get_at((int(self.c5[0]),int(self.c5[1]))).a!=0:
        self.c5 = move((self.c5[0],self.c5[1]),self.angle-90,10)
    while bg4.get_at((int(self.c5[0]),int(self.c5[1]))).a==0:
        self.c5 = move((self.c5[0],self.c5[1]),self.angle-90,-1)

    self.d1 = int(calculateDistance(self.center[0], self.center[1], self.c1[0], self.c1[1]))
    self.d2 = int(calculateDistance(self.center[0], self.center[1], self.c2[0], self.c2[1]))
    self.d3 = int(calculateDistance(self.center[0], self.center[1], self.c3[0], self.c3[1]))
    self.d4 = int(calculateDistance(self.center[0], self.center[1], self.c4[0], self.c4[1]))
    self.d5 = int(calculateDistance(self.center[0], self.center[1], self.c5[0], self.c5[1]))

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

  def collision(self):
      bg4 = self.collision_surface or collision_surface
      if (bg4.get_at((int(self.a[0]),int(self.a[1]))).a==0) or (bg4.get_at((int(self.b[0]),int(self.b[1]))).a==0) or (bg4.get_at((int(self.c[0]),int(self.c[1]))).a==0) or (bg4.get_at((int(self.d[0]),int(self.d[1]))).a==0):
        return True
      else:
        return False

  def set_collision_surface(self, surface):
      self.collision_surface = surface

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
