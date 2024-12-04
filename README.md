# BlueNaaS-SingleCell

<img src="BlueNaaS-SingleCell.jpg" width="800"/>

Blue-Neuroscience-as-a-Service-SingleCell is an open source web application.
It enables users to quickly visualize single cell model morphologies in 3D
or as a dendrogram. Using a simple web user interface, single cell simulations
can be easily configured and launched, producing voltage traces from selected
compartments.

## Examples
You can use the application on the EBRAINS platform at https://ebrains-cls-interactive.github.io/online-use-cases.html by selecting "Single Cell InSilico Experiments". You can also follow this [direct link](https://blue-naas-bsp-epfl.apps.hbp.eu/#/url/hippocampus_optimization/rat/CA1/v4.0.5/optimizations_Python3/CA1_pyr_cACpyr_mpg141208_B_idA_20190328144006/CA1_pyr_cACpyr_mpg141208_B_idA_20190328144006.zip?use_cell=cell_seed3_0.hoc&bluenaas=true).

<img src="images/output.png" width="800"/>

## Documentation
The user documentation for the service can be found [here](https://ebrains-cls-interactive.github.io/docs/online_usecases/single_cell_in_silico/single_cell_clamp/single_cell_clamp.html).

From version 2.0 we are using [BlueCelluLab](https://github.com/BlueBrain/BlueCelluLab) library to run simulations.

To get the code for legacy (neuron) version check out [v1 branch](https://bbpgitlab.epfl.ch/project/sbo/bluenaas-single-cell/-/tree/v1)

## Development

1. After cloning or forking the repository, you can use poetry to install the dependencies:
```bash
poetry install
```

2. Build Bluenaas service image (only needed the first time or when a new dependency is added):
```bash
make build
```

3. Start docker services. This spins up a local instance of services (such as celery workers, redis, etc) needed to mimic the distributed environment locally.
```bash
make start
```

## Simulate your own models.
You can upload your own models and run single cell simulations. The `.zip` file format must be:
model_name.zip
  - model_name
    - mechanisms /
      - *.mod files
    - morphology /
      - morphology file loaded by cell.hoc
    - cell.hoc

## Citation
When you use the BlueNaaS-SingleCell software, we ask you to cite the following:
[![DOI](https://zenodo.org/badge/doi/10.5281/zenodo.7784792.svg)](https://doi.org/10.5281/zenodo.7784792)

## Funding & Acknowledgment
The development of this software was supported by funding to the Blue Brain Project,
a research center of the École polytechnique fédérale de Lausanne (EPFL),
from the Swiss government's ETH Board of the Swiss Federal Institutes of Technology
and from the Human Brain Project's Specific Grant Agreement 3.

Copyright (c) 2022-2024 Blue Brain Project/EPFL
