# Environment and Dependencies

Offline: Python 3.9, NumPy, and Matplotlib. Historical model analysis also needs SciPy/pandas; PDF auditing needs PyMuPDF. Versions are in `requirements-lock.txt`.

Hardware: NVIDIA Jetson, matching CUDA/nvcc, g++, make, Eigen3 headers, pthread, Linux shared memory, and device access. Power backends are implemented in `Common/jetson`.

The inspected device was a Jetson Orin Nano Super with CUDA 12.6 and L4T 36.4.3. The paper specifies CUDA 12.0; the current installation does not establish the historical environment.

Current power code supports tegrastats, jtop, and INA260. The presence of INA260 code alone does not establish the sensor used for every historical log.
