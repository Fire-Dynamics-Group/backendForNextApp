# from typing import List
# from pydantic import BaseModel

# class Point(BaseModel):
#     x: float
#     y: float

# class Element(BaseModel):
#     type: str
#     points: List[Point]
#     comments: str

# class ConvertedElement(BaseModel):
#     finalPoints: List[Point]
#     comments: str

# mockConvertedPoints = [ConvertedElement(finalPoints=[Point(x=0.2, y=0.0), Point(x=0.2, y=5.2), Point(x=0.0, y=5.2), Point(x=0.0, y=5.8), Point(x=9.7, y=5.8), Point(x=9.7, y=5.6), Point(x=10.0, y=5.6), Point(x=10.0, y=2.4), Point(x=10.4, y=2.4), Point(x=10.4, y=0.1), Point(x=7.3, y=0.1), Point(x=7.3, y=0.0), Point(x=0.2, y=0.0)], comments='obstruction'), ConvertedElement(finalPoints=[Point(x=10.0, y=5.5), Point(x=10.0, y=4.2)], comments='opening'), ConvertedElement(finalPoints=[Point(x=10.4, y=2.4), Point(x=10.4, y=0.1)], comments='opening')]

mockTimeEqElements = [
    {
        "id": 0,
        "finalPoints": [
            {
                "x": 0.2,
                "y": 0
            },
            {
                "x": 0.2,
                "y": 5.2
            },
            {
                "x": 0,
                "y": 5.2
            },
            {
                "x": 0,
                "y": 5.8
            },
            {
                "x": 9.7,
                "y": 5.8
            },
            {
                "x": 9.7,
                "y": 5.6
            },
            {
                "x": 10,
                "y": 5.6
            },
            {
                "x": 10,
                "y": 2.4
            },
            {
                "x": 10.4,
                "y": 2.4
            },
            {
                "x": 10.4,
                "y": 0.1
            },
            {
                "x": 7.3,
                "y": 0.1
            },
            {
                "x": 7.3,
                "y": 0
            },
            {
                "x": 0.2,
                "y": 0
            }
        ],
        "comments": "obstruction"
    },
    {
        "id": 1,
        "finalPoints": [
            {
                "x": 10,
                "y": 5.5
            },
            {
                "x": 10,
                "y": 4.2
            }
        ],
        "comments": "opening"
    },
    {
        "id": 2,
        "finalPoints": [
            {
                "x": 10.4,
                "y": 2.4
            },
            {
                "x": 10.4,
                "y": 0.1
            }
        ],
        "comments": "opening"
    }
]


if __name__ == '__main__':
    import matplotlib.pyplot as plt
    for step in mockTimeEqElements:
        path = [[current['x'], current['y']] for current in step["finalPoints"]]
        plt.plot(*zip(*path))
    plt.show()
    pass