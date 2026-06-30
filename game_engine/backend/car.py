import math

import numpy as np
import pygame

from game_engine.backend.geometry import calculateDistance, move, rotation, sigmoid
from game_engine.backend.settings import COLOR_LINE, MAX_SPEED, WHITE
from game_engine.backend.track import TrackGeometry
from shared.contracts import DEFAULT_EVOLUTION_SEED

collision_surface = None
default_car_image = None
maxspeed = MAX_SPEED
DEFAULT_MLP_INIT_SEED = DEFAULT_EVOLUTION_SEED


def configure_car(collision_map, car_image, max_speed=MAX_SPEED):
    global collision_surface, default_car_image, maxspeed
    collision_surface = collision_map
    default_car_image = car_image
    maxspeed = max_speed


def set_collision_map(collision_map):
    global collision_surface
    collision_surface = collision_map


class Car:
  """A car whose root MLP seed stays attached when a shared RNG is used."""

  def __init__(
    self,
    sizes,
    mlp_init_seed: int | None = DEFAULT_MLP_INIT_SEED,
    *,
    mlp_init_rng: np.random.Generator | None = None,
  ):
    self.score = 0
    self.fitness_score = 0.0
    self.num_layers = len(sizes)
    self.sizes = sizes
    self._mlp_init_seed: int | None = None
    if mlp_init_rng is not None:
      self._mlp_init_seed = self._validated_mlp_init_seed(mlp_init_seed)
      self._initialize_mlp_parameters(mlp_init_rng)
    else:
      self.mlp_init_seed = mlp_init_seed
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
    self.velocity = 0.0
    self.acceleration = 0
    self.angle = 180
    self.collided = False
    self.color = WHITE
    self.car_image = default_car_image
    # Existing training code configures a global map. Replays can override it per car.
    self.collision_surface = collision_surface

  @property
  def mlp_init_seed(self) -> int | None:
    return self._mlp_init_seed

  @mlp_init_seed.setter
  def mlp_init_seed(self, seed: int | None):
    seed = self._validated_mlp_init_seed(seed)
    self._mlp_init_seed = seed
    self._initialize_mlp_parameters(np.random.default_rng(seed))

  @staticmethod
  def _validated_mlp_init_seed(seed: int | None) -> int | None:
    if seed is not None:
      if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise TypeError("mlp_init_seed must be an integer or None")
      if seed < 0:
        raise ValueError("mlp_init_seed cannot be negative")
      seed = int(seed)
    return seed

  def _initialize_mlp_parameters(self, rng: np.random.Generator):
    # Preserve draw order for reproducible evolution: W0, W1, ..., b0, b1, ...
    self.weights = [
      rng.standard_normal((y, x))
      for x, y in zip(self.sizes[:-1], self.sizes[1:])
    ]
    self.biases = [rng.standard_normal((y, 1)) for y in self.sizes[1:]]

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
    surface = self.collision_surface or collision_surface
    if surface is None:
        return False
    x, y = int(point[0]), int(point[1])
    width, height = surface.get_size()
    return (
        0 <= x < width
        and 0 <= y < height
        and surface.get_at((x, y)).a != 0
    )

  def _containment_check(self, track: TrackGeometry | None):
    """Prefer the collision bitmap for hot-path sensor and collision checks."""
    if self.collision_surface is not None or collision_surface is not None:
        return self._surface_contains
    if track is not None:
        return track.contains
    return self._surface_contains

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
    contains = self._containment_check(track)
    step = (
        10
        if self.collision_surface is not None or collision_surface is not None
        else 4
    )
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
      contains = self._containment_check(track)
      return not all(contains(corner) for corner in (self.a, self.b, self.c, self.d))

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
