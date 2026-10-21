"""Cells to pixels on the GPU.

The font is uploaded once as an atlas. Each frame uploads only the cell grid,
four bytes per cell, and a fragment shader draws every pixel the way fbcon
would: the glyph bit picks fg or bg, and the cursor XORs its rows.
"""

import os

import numpy as np

# GTK draws through EGL on Wayland. PyOpenGL has to look up GL there too.
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")

from OpenGL import GL

ATLAS_COLS = 32

VERTEX = """
void main() {
    // One triangle that covers the whole viewport.
    vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

FRAGMENT = """
precision highp float;
precision highp int;
uniform sampler2D atlas;
uniform sampler2D cells;
uniform vec3 palette[16];
uniform ivec2 cell_size;
uniform ivec2 grid;
uniform int height_px;
uniform int cursor_rows;
out vec4 color;

void main() {
    ivec2 p = ivec2(int(gl_FragCoord.x), height_px - 1 - int(gl_FragCoord.y));
    ivec2 c = p / cell_size;
    if (c.x >= grid.x || c.y >= grid.y) {
        color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    ivec4 v = ivec4(texelFetch(cells, c, 0) * 255.0 + 0.5);
    int glyph = v.r + v.g * 256;
    ivec2 inner = p - c * cell_size;
    ivec2 a = ivec2((glyph % ATLAS_COLS) * cell_size.x + inner.x,
                    (glyph / ATLAS_COLS) * cell_size.y + inner.y);
    bool on = texelFetch(atlas, a, 0).r > 0.5;
    if (v.a != 0 && inner.y >= cell_size.y - cursor_rows) {
        on = !on;
    }
    color = vec4(on ? palette[v.b & 15] : palette[v.b >> 4], 1.0);
}
"""


class GLRenderer:
    """Draws a Buffer inside a Gtk.GLArea's render callback."""

    def __init__(self, font, palette):
        self.font = font
        self.palette = np.array(palette, dtype=np.float32).reshape(16, 3) / 255.0
        self.cursor_rows = 1 if font.height < 10 else 2
        self.cells = None
        self.cells_changed = False
        self.program = None

    def update(self, buf, cursor=None):
        """Pack the buffer into the cell grid. Returns True if it changed."""
        glyph = self.font.glyph_indices(buf.ch)
        cells = np.empty((buf.height, buf.width, 4), dtype=np.uint8)
        cells[..., 0] = glyph & 0xFF
        cells[..., 1] = glyph >> 8
        cells[..., 2] = buf.fg | (buf.bg << 4)
        cells[..., 3] = 0
        if cursor is not None and 0 <= cursor[0] < buf.width and 0 <= cursor[1] < buf.height:
            cells[cursor[1], cursor[0], 3] = 1
        if self.cells is not None and self.cells.shape == cells.shape and (self.cells == cells).all():
            return False
        self.cells = cells
        self.cells_changed = True
        return True

    def realize(self, use_es):
        header = "#version 300 es\n" if use_es else "#version 150\n"
        fragment = FRAGMENT.replace("ATLAS_COLS", str(ATLAS_COLS))
        self.program = GL.glCreateProgram()
        for kind, source in ((GL.GL_VERTEX_SHADER, VERTEX), (GL.GL_FRAGMENT_SHADER, fragment)):
            shader = GL.glCreateShader(kind)
            GL.glShaderSource(shader, header + source)
            GL.glCompileShader(shader)
            if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
                raise RuntimeError(GL.glGetShaderInfoLog(shader).decode())
            GL.glAttachShader(self.program, shader)
        GL.glLinkProgram(self.program)
        if not GL.glGetProgramiv(self.program, GL.GL_LINK_STATUS):
            raise RuntimeError(GL.glGetProgramInfoLog(self.program).decode())
        self.vao = GL.glGenVertexArrays(1)
        self.atlas_tex, self.cells_tex = GL.glGenTextures(2)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)

        # Atlas: ATLAS_COLS glyphs per row, one byte per pixel.
        fw, fh = self.font.width, self.font.height
        n = len(self.font.glyphs)
        rows = -(-n // ATLAS_COLS)
        atlas = np.zeros((rows * ATLAS_COLS, fh, fw), dtype=np.uint8)
        atlas[:n] = self.font.glyphs * 255
        atlas = atlas.reshape(rows, ATLAS_COLS, fh, fw).transpose(0, 2, 1, 3)
        atlas = np.ascontiguousarray(atlas.reshape(rows * fh, ATLAS_COLS * fw))
        self._texture(self.atlas_tex, GL.GL_R8, GL.GL_RED, atlas)
        self.cells_changed = True

    def _texture(self, tex, internal, fmt, data):
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        h, w = data.shape[:2]
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, internal, w, h, 0, fmt, GL.GL_UNSIGNED_BYTE, data)

    def unrealize(self):
        if self.program is not None:
            GL.glDeleteTextures([self.atlas_tex, self.cells_tex])
            GL.glDeleteVertexArrays(1, [self.vao])
            GL.glDeleteProgram(self.program)
            self.program = None

    def render(self, width_px, height_px):
        GL.glViewport(0, 0, width_px, height_px)
        GL.glClearColor(0.0, 0.0, 0.0, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        if self.cells is None or self.program is None:
            return
        if self.cells_changed:
            self._texture(self.cells_tex, GL.GL_RGBA8, GL.GL_RGBA, self.cells)
            self.cells_changed = False
        p = self.program
        GL.glUseProgram(p)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.atlas_tex)
        GL.glUniform1i(GL.glGetUniformLocation(p, "atlas"), 0)
        GL.glActiveTexture(GL.GL_TEXTURE1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.cells_tex)
        GL.glUniform1i(GL.glGetUniformLocation(p, "cells"), 1)
        GL.glUniform3fv(GL.glGetUniformLocation(p, "palette"), 16, self.palette)
        GL.glUniform2i(GL.glGetUniformLocation(p, "cell_size"), self.font.width, self.font.height)
        rows, cols = self.cells.shape[:2]
        GL.glUniform2i(GL.glGetUniformLocation(p, "grid"), cols, rows)
        GL.glUniform1i(GL.glGetUniformLocation(p, "height_px"), height_px)
        GL.glUniform1i(GL.glGetUniformLocation(p, "cursor_rows"), self.cursor_rows)
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
