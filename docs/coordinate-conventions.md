# FDS coordinate convention (backend)

FDS coordinates are the plain, human view of the drawing:

> **+x → RIGHT, +y → TOP of the screen, +z → OUT of the page (toward you).**

Standard right-handed, north at the top. Everything this service emits in the
`.fds` file (walls, stairs, sensors, doors, meshes) lives in that space.

## The backend's job: flip Y once

The drawing **canvas** the frontend sends is **y-DOWN** (pixel rows: y=0 is the
TOP of the screen). FDS is **y-UP**. So `testFunction` flips Y exactly once,
right after scaling pixels → metres (`fds.py`, ~L1580–1589):

```python
origin = returnOrigin(elements)
elements = makeElementsRelativeToOrigin(elements, origin)
elements = convertElPointsToCoords(elements, px_per_m)   # pixels -> metres
# Flip Y: canvas y=0 is top, FDS y=0 is bottom
max_y = max(p["y"] for el in elements for p in el["points"])
for el in elements:
    for p in el["points"]:
        p["y"] = max_y - p["y"]
```

After this, an element drawn at the **top** of the plan has the **largest**
`y_fds`. x passes through; z is height.

## Rules

- **This flip is mandatory and there must be exactly one of it.** Every producer
  downstream (stairs, sensors, fire, doors, meshes) assumes y-up FDS. Do not
  remove it, do not duplicate it, and do not "fix" a 2D/3D mismatch by changing
  its sign — the frontend renderer adapts to the camera, not this file.
- If the 3D view ever looks mirrored top↔bottom vs the plan, the bug is in the
  **frontend** render mapping, not here. See the full chain (R1–R6) in the
  frontend repo: `upload-canvas/docs/orientation-verification.md`.
