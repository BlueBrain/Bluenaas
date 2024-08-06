"""Util."""

import json
import re
import subprocess
import tarfile
import zipfile
from io import BytesIO
from pathlib import Path
import random
import numpy as np
from loguru import logger as L
from bluenaas.domains.morphology import LocationData
from bluenaas.domains.simulation import SynapseSimulationConfig

PADDING = 2.0


class NumpyAwareJSONEncoder(json.JSONEncoder):
    """Serialize numpy to json."""

    def default(self, o):
        """Handle numpy lists."""
        if isinstance(o, np.ndarray) and o.ndim == 1:
            return o.tolist()
        return json.JSONEncoder.default(self, o)


def is_spine(sec_name):
    """Check if "spine" suffix is present in section name."""
    return "spine" in sec_name


def _extract_model(model_path):
    """Extract xz model to tmp folder."""
    with tarfile.open(model_path) as f:
        f.extractall("/opt/blue-naas/tmp")
    return next(Path("/opt/blue-naas/tmp").iterdir())


def extract_zip_model(content, model_uuid):
    """Extract zip model to models folder."""
    with zipfile.ZipFile(BytesIO(content), "r") as zip_ref:
        zip_ref.extractall(Path("/opt/blue-naas/models") / model_uuid)


def model_exists(model_uuid):
    """Check if model exists in the mounted volume."""
    model_path = Path("/opt/blue-naas/models") / model_uuid
    return model_path.exists()


def locate_model(model_uuid) -> Path | None:
    """Locate model according to the priorities.

    First will look-up in models folder, then in the tmp folder, where unzipped models are going.

    Returns:
        pathlib.Path: path for the model

    Raises:
        Exception: if model not found
    """
    model_path = Path("/opt/blue-naas/models") / model_uuid
    if model_path.suffixes == [".tar", ".xz"]:
        return _extract_model(model_path)
    if model_path.exists():
        return model_path
    model_path = (
        Path("/opt/blue-naas/tmp") / model_uuid
    )  # model catalog models go in here
    if model_path.exists():
        return model_path
    return None


def compile_mechanisms(model_path, no_throw=False):
    """Compile model mechanisms."""
    # Bail out if the mechanisms are already compiled
    compiled_path = model_path / "x86_64"
    if compiled_path.is_dir():
        L.debug("Found already compiled mechanisms")
        return

    mech_path = model_path / "mechanisms"
    if not mech_path.is_dir():
        if not no_throw:
            raise Exception(
                "Folder not found! Expecting 'mechanisms' folder in the model!"
            )
    else:
        cmd = ["nrnivmodl", "mechanisms"]
        compilation_output = subprocess.check_output(cmd, cwd=model_path)
        L.info(compilation_output.decode())


def get_sec_name(template_name, sec):
    """Get section name."""
    return sec.name().replace(template_name + ".", "")


def get_morph_data(cell):
    """Get 3d morphology points, for each section, align soma at center."""
    x = []
    y = []
    z = []
    arc = []
    for sec in cell.sections.values():
        sec_point_count = sec.n3d()

        x_ = np.empty(sec_point_count)
        y_ = np.empty(sec_point_count)
        z_ = np.empty(sec_point_count)
        arc_ = np.empty(sec_point_count)

        for i in range(sec_point_count):
            x_[i] = sec.x3d(i)
            y_[i] = sec.y3d(i)
            z_[i] = sec.z3d(i)
            arc_[i] = sec.arc3d(i)

        x.append(x_)
        y.append(y_)
        z.append(z_)
        arc.append(arc_)

    if len(x) > 1:  # more than only just a soma
        soma_mean = x[0].mean(), y[0].mean(), z[0].mean()
        for i, _ in enumerate(x):
            x[i] -= soma_mean[0]
            y[i] -= soma_mean[1]
            z[i] -= soma_mean[2]

    return x, y, z, arc


def get_sec_name_seg_idx(template_name, seg):
    """Get section name from segment."""
    name = seg.sec.name().replace(template_name + ".", "")
    seg_idx = int(np.fix(seg.sec.nseg * seg.x * 0.9999999))
    return name, seg_idx


def convert_numpy_dict_to_standard_dict(numpy_dict):
    """Convert numpy dict to standard dict."""
    standard_dict = {}
    for key, value in numpy_dict.items():
        if isinstance(value, np.ndarray):
            standard_dict[key] = value.tolist()
        else:
            standard_dict[key] = value
    return standard_dict


def get_sections(cell) -> tuple[list, dict[str, LocationData]]:
    from neuron import h

    """Get section segment cylinders and spines."""
    # pylint: disable=too-many-statements,too-many-locals
    all_sec_array = []
    all_sec_map = {}
    spine_start = 0
    x, y, z, arc = get_morph_data(cell)

    for sec_idx, sec in enumerate(cell.sections.values()):
        sec_name = get_sec_name(cell.hocname, sec)
        # sec_pre = cell.get_psection(section_id=sec_name).hsection
        sec_data = {"index": sec_idx}
        sec_data["name"] = sec_name

        # We need to save the `isec` of a section because BlueCelluLab does not accept a string as POST_SECTION_ID when `add_replay_synapse` is called
        sec_data["neuron_section_id"] = cell.get_psection(sec.name()).isec
        all_sec_map[sec_name] = sec_data
        all_sec_array.append(sec)

        sec_data["nseg"] = sec.nseg
        seg_x_delta = 0.5 / sec.nseg

        if len(arc[sec_idx]) > 0:
            length = arc[sec_idx] / sec.L

            seg_x = np.empty(sec.nseg)
            seg_diam = np.empty(sec.nseg)
            seg_length = np.empty(sec.nseg)
            for i, seg in enumerate(sec):
                seg_x[i] = seg.x
                seg_diam[i] = seg.diam
                seg_length[i] = sec.L / sec.nseg

            seg_x_start = seg_x - seg_x_delta
            seg_x_end = seg_x + seg_x_delta

            sec_data["xstart"] = np.interp(seg_x_start, length, x[sec_idx])
            sec_data["xend"] = np.interp(seg_x_end, length, x[sec_idx])
            sec_data["xcenter"] = (sec_data["xstart"] + sec_data["xend"]) / 2.0
            sec_data["xdirection"] = sec_data["xend"] - sec_data["xstart"]
            sec_data["ystart"] = np.interp(seg_x_start, length, y[sec_idx])
            sec_data["yend"] = np.interp(seg_x_end, length, y[sec_idx])
            sec_data["ycenter"] = (sec_data["ystart"] + sec_data["yend"]) / 2.0
            sec_data["ydirection"] = sec_data["yend"] - sec_data["ystart"]

            sec_data["zstart"] = np.interp(seg_x_start, length, z[sec_idx])
            sec_data["zend"] = np.interp(seg_x_end, length, z[sec_idx])
            sec_data["zcenter"] = (sec_data["zstart"] + sec_data["zend"]) / 2.0
            sec_data["zdirection"] = sec_data["zend"] - sec_data["zstart"]

            sec_data["segx"] = seg_x
            sec_data["diam"] = seg_diam
            sec_data["length"] = seg_length
            sec_data["distance"] = np.sqrt(
                sec_data["xdirection"] * sec_data["xdirection"]
                + sec_data["ydirection"] * sec_data["ydirection"]
                + sec_data["zdirection"] * sec_data["zdirection"]
            )

            sec_data["distance_from_soma"] = h.distance(cell.soma(0), sec(0))
            sec_data["sec_length"] = sec.L
            segments_offset: list[float] = []
            for seg in sec.allseg():
                segments_offset.append(float(seg.x))
            sec_data["neuron_segments_offset"] = segments_offset

            # if is_spine(sec_name):  # spine location correction
            #     assert sec_data["nseg"] == 1, "spine sections should have one segment"
            #     parent_seg = sec.parentseg()
            #     parent_sec_name, parent_seg_idx = get_sec_name_seg_idx(
            #         cell.hocname, parent_seg
            #     )
            #     parent_sec = all_sec_map[parent_sec_name]
            #     if is_spine(parent_sec_name):
            #         # another section in spine -> continue in the direction of the parent
            #         dir_ = np.array(
            #             [
            #                 parent_sec["xdirection"][parent_seg_idx],
            #                 parent_sec["ydirection"][parent_seg_idx],
            #                 parent_sec["zdirection"][parent_seg_idx],
            #             ]
            #         )
            #         dir_norm = dir_ / np.linalg.norm(dir_)
            #         sec_data["xstart"][0] = parent_sec["xend"][parent_seg_idx]
            #         sec_data["ystart"][0] = parent_sec["yend"][parent_seg_idx]
            #         sec_data["zstart"][0] = parent_sec["zend"][parent_seg_idx]
            #         spine_end = spine_start + dir_norm * sec_data["length"][0]
            #         sec_data["xend"][0] = spine_end[0]
            #         sec_data["yend"][0] = spine_end[1]
            #         sec_data["zend"][0] = spine_end[2]
            #     else:
            #         seg_x_step = 1 / parent_seg.sec.nseg
            #         seg_x_offset_normalized = (
            #             parent_seg.x - seg_x_step * parent_seg_idx
            #         ) / seg_x_step
            #         parent_start = np.array(
            #             [
            #                 parent_sec["xstart"][parent_seg_idx],
            #                 parent_sec["ystart"][parent_seg_idx],
            #                 parent_sec["zstart"][parent_seg_idx],
            #             ]
            #         )
            #         parent_dir = np.array(
            #             [
            #                 parent_sec["xdirection"][parent_seg_idx],
            #                 parent_sec["ydirection"][parent_seg_idx],
            #                 parent_sec["zdirection"][parent_seg_idx],
            #             ]
            #         )
            #         parent_dir = parent_dir / np.linalg.norm(parent_dir)
            #         pos_in_parent = parent_start + parent_dir * seg_x_offset_normalized
            #         # choose random spin orientation orthogonal to the parent section
            #         random = np.random.uniform(-1, 1, 3)
            #         dir_ = np.cross(parent_dir, random)
            #         dir_norm = dir_ / np.linalg.norm(dir_)
            #         spine_start = (
            #             pos_in_parent
            #             + dir_norm * parent_sec["diam"][parent_seg_idx] / 2
            #         )
            #         sec_data["xstart"][0] = spine_start[0]
            #         sec_data["ystart"][0] = spine_start[1]
            #         sec_data["zstart"][0] = spine_start[2]
            #         spine_end = spine_start + dir_norm * sec_data["length"][0]
            #         sec_data["xend"][0] = spine_end[0]
            #         sec_data["yend"][0] = spine_end[1]
            #         sec_data["zend"][0] = spine_end[2]

            #     sec_data["xdirection"][0] = sec_data["xend"][0] - sec_data["xstart"][0]
            #     sec_data["ydirection"][0] = sec_data["yend"][0] - sec_data["ystart"][0]
            #     sec_data["zdirection"][0] = sec_data["zend"][0] - sec_data["zstart"][0]
            #     sec_data["xcenter"] = (sec_data["xstart"] + sec_data["xend"]) / 2.0
            #     sec_data["ycenter"] = (sec_data["ystart"] + sec_data["yend"]) / 2.0
            #     sec_data["zcenter"] = (sec_data["zstart"] + sec_data["zend"]) / 2.0

    # TODO: rework this
    all_sec_map_no_numpy = {}
    for section, values in all_sec_map.items():
        all_sec_map_no_numpy.update(
            {section: convert_numpy_dict_to_standard_dict(values)}
        )

    return all_sec_array, all_sec_map_no_numpy


def set_sec_dendrogram(template_name, sec, data):
    """Set section dendrogram into data dictionary."""
    data["name"] = get_sec_name(template_name, sec)
    data["height"] = sec.L + sec.nseg * PADDING

    segments = []
    data["segments"] = segments

    max_seg_diam = 0
    for seg in sec:
        max_seg_diam = max(max_seg_diam, seg.diam)
        segments.append({"length": sec.L / sec.nseg, "diam": seg.diam})
    data["width"] = max_seg_diam + PADDING * 2

    data["sections"] = []
    for child_sec in sec.children():
        child_sec_data = {}
        data["sections"].append(child_sec_data)
        set_sec_dendrogram(template_name, child_sec, child_sec_data)

    if len(data["sections"]) == 0:
        total_width = data["width"]
    else:
        total_width = 0

    for s in data["sections"]:
        total_width += s["total_width"]
    data["total_width"] = total_width


def get_syns(nrn, path, template_name, all_sec_map):
    """Get synapses."""
    synapses = {}
    synapses_meta = json.loads(path.read_bytes())
    for synapse_type in synapses_meta.keys():
        for synapse in synapses_meta[synapse_type]:
            if hasattr(nrn.h, synapse):
                for syn in getattr(nrn.h, synapse):
                    id_ = re.search(r"\[(\d+)\]", str(syn)).group(1)
                    seg = syn.get_segment()
                    sec = seg.sec
                    sec_name = get_sec_name(template_name, sec)
                    # 0.9999999 just so that seg_idx is not equal to 1
                    seg_idx = int(
                        np.fix(all_sec_map[sec_name]["nseg"] * seg.x * 0.9999999)
                    )
                    if synapses.get(synapse_type):
                        synapses[synapse_type].append(
                            {"sec_name": sec_name, "seg_idx": seg_idx, "id": id_}
                        )
                    else:
                        synapses[synapse_type] = [
                            {"sec_name": sec_name, "seg_idx": seg_idx, "id": id_}
                        ]
    return synapses


def point_between_vectors(
    vec1: np.ndarray, vec2: np.ndarray, position: float
) -> np.ndarray:
    # Compute the random point as an interpolation between vec1 and vec2
    random_point = (1 - position) * vec1 + position * vec2

    return random_point


def perpendicular_vector(v: np.ndarray) -> np.ndarray:
    """
    Finds a perpendicular vector to the given vector v using the cross product method.

    Args:
    v: numpy array, the input vector.

    Returns:
    numpy array, a vector perpendicular to v.
    """
    # Choose an arbitrary vector that is not parallel to v
    if np.all(v == 0):
        raise ValueError("Cannot find a perpendicular vector for the zero vector")

    # Choose a vector that is not parallel
    if v[0] == 0 and v[1] == 0:
        # If the vector is along the z-axis, choose a vector in the xy-plane
        arbitrary_vector = np.array([1, 0, 0])
    else:
        arbitrary_vector = np.array([0, 0, 1])

    # Compute the cross product to get a perpendicular vector
    perp_vector = np.cross(v, arbitrary_vector)

    return perp_vector


def set_vector_length(vector: np.ndarray, length: float) -> np.ndarray:
    # Compute the magnitude (length) of the original vector
    magnitude = np.linalg.norm(vector)

    if magnitude == 0:
        raise ValueError("Cannot set length for a zero vector")

    # Normalize the vector (make it a unit vector)
    unit_vector = vector / magnitude

    # Scale the unit vector to the desired length
    scaled_vector = unit_vector * length

    return scaled_vector


def project_vector(v1: np.ndarray, v2: np.ndarray) -> np.ndarray:
    """
    Projects vector v1 onto vector v2.

    Args:
    v1: numpy array, the vector to be projected.
    v2: numpy array, the vector onto which v1 is projected.

    Returns:
    numpy array, the projection of v1 onto v2.
    """
    # Compute the dot product of v1 and v2
    dot_product = np.dot(v1, v2)

    # Compute the dot product of v2 with itself
    magnitude_squared = np.dot(v2, v2)

    # Compute the projection scalar
    projection_scalar = dot_product / magnitude_squared

    # Compute the projection vector
    projection_vector = projection_scalar * v2

    return projection_vector


def random_target_segment(nSeg: int):
    return random.randint(0, nSeg)


def generate_pre_spiketrain(syn_input_config: SynapseSimulationConfig) -> np.array:
    frequency = syn_input_config.frequency
    duration = syn_input_config.duration
    delay = syn_input_config.delay

    spike_interval = 1000 / frequency
    spiketrain_size = int(round(float(duration) / 1000 * frequency))
    spiketrain_raw = np.insert(
        np.random.poisson(spike_interval, spiketrain_size)[:-1], 0, 0
    )
    return np.cumsum(spiketrain_raw) + delay
