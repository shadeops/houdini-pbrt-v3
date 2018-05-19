
class PBRTState(object):
    def __init__(self):
        self.shading_nodes = set()
        self.medium_nodes = set()
        self.exterior = None

    def reset(self):
        self.shading_nodes.clear()
        self.medium_nodes.clear()
        self.exterior = None

scene_state = PBRTState()

