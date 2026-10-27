import os
import sys

# Os módulos do projeto ficam em src/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

# Testes nunca devem controlar o mouse de verdade
os.environ.pop('DISPLAY', None)
os.environ.pop('WAYLAND_DISPLAY', None)
