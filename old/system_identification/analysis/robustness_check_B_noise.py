import numpy as np


def solve_lqr_gain(A, B, Q, R, horizon=500):
    """
    Mirror the finite-horizon Riccati recursion in controller.cc.

    C++ computes a positive gain matrix, but the actual control update applies -gain.
    Therefore, with this K, the closed-loop matrix is:

        A_cl = A - B @ K
    """
    n = A.shape[0]

    # Scaling, same as controller.cc
    Sx = np.eye(n)
    Su = np.eye(n)

    # State scaling: RTR errors / power error
    for i in range(n - 1):
        Sx[i, i] = 10.0
    Sx[n - 1, n - 1] = 1.0

    # Input scaling: task-period changes / GPU-frequency changes
    for i in range(n - 1):
        Su[i, i] = 1.0
    Su[n - 1, n - 1] = 100.0

    Sx_inv = np.linalg.inv(Sx)

    As = Sx_inv @ A @ Sx
    Bs = Sx_inv @ B @ Su
    Qs = Sx.T @ Q @ Sx
    Rs = Su.T @ R @ Su

    P = Qs.copy()
    K_scaled = np.zeros((n, n))

    for _ in range(horizon):
        M = Rs + Bs.T @ P @ Bs
        K_scaled = np.linalg.solve(M, Bs.T @ P @ As)

        P_next = As.T @ P @ As - As.T @ P @ Bs @ K_scaled + Qs
        P = 0.5 * (P_next + P_next.T)

        if not np.all(np.isfinite(P)):
            raise RuntimeError("Riccati recursion produced NaN/Inf.")

    # Convert scaled gain back to original coordinates
    K_unscaled = Su @ K_scaled @ Sx_inv
    return K_unscaled


def build_matrices(numtasks=3):
    """
    Build A, B, Q, R using the paper-style B matrix.

    Task order:
        0 = hist
        1 = stereo
        2 = mm

    Paper-style task-rate block:
        diagonal = 0
        off-diagonal = identified cross-task coupling slopes
    """
    if numtasks != 3:
        raise ValueError("This paper-style B is currently filled for exactly 3 tasks: hist, stereo, mm.")

    N = numtasks
    n = N + 1

    # A matrix
    A = np.eye(n) * 0.95

    # B matrix
    B = np.zeros((n, n))

    # ============================================================
    # Paper-style off-diagonal task-rate block
    # rows = observed task RT_i
    # cols = swept task_j
    #
    # Original fit.py output order:
    #   rows/cols = hist, mm, stereo
    #
    # Reordered here to:
    #   rows/cols = hist, stereo, mm
    # ============================================================

    # hist row
    B[0, 0] = 0.0
    B[0, 1] = -0.047925   # hist from stereo
    B[0, 2] = -0.051977   # hist from mm

    # stereo row
    B[1, 0] = -0.039721   # stereo from hist
    B[1, 1] = 0.0
    B[1, 2] = -0.055639   # stereo from mm

    # mm row
    B[2, 0] = -0.029773   # mm from hist
    B[2, 1] = -0.067892   # mm from stereo
    B[2, 2] = 0.0

    # Frequency -> RTR coupling
    # order: hist, stereo, mm
    B[0, N] = 0.06238100
    B[1, N] = 0.06804800
    B[2, N] = 0.07260400

    # Task-period -> power coupling
    # order: hist, stereo, mm
    B[N, 0] = 0.02220753300
    B[N, 1] = 0.01107223000
    B[N, 2] = 0.02852230300

    # Frequency -> power coupling
    # Negative because power error is P_set - P_measured
    B[N, N] = -0.00116413

    # Q and R
    q_scale = 8.0
    r_scale = 8.0

    Q = np.zeros((n, n))
    for i in range(N):
        Q[i, i] = 20.0 / q_scale
    Q[N, N] = 10.0 / (q_scale * 4.0)

    R = np.zeros((n, n))
    for i in range(N):
        R[i, i] = 1.0 / r_scale
    R[N, N] = 10.0 / (r_scale * 4.0)

    return A, B, Q, R


def closed_loop_eigs(A, B, K_fixed):
    """
    Since the C++ control update applies -gain:

        A_cl = A - B @ K_fixed
    """
    A_cl = A - B @ K_fixed
    eigvals = np.linalg.eigvals(A_cl)
    max_abs = np.max(np.abs(eigvals))
    stable = max_abs < 1.0
    return eigvals, max_abs, stable


def perturb_A_diagonal_bounded(A, eps, rng):
    """
    Bounded relative perturbation on diagonal entries of A only.

        A_noisy[i,i] = A[i,i] * (1 + delta_i)
        delta_i ~ Uniform[-eps, eps]

    Since A = 0.95 I and eps = 0.05, the diagonal range is:
        0.95 * [0.95, 1.05] = [0.9025, 0.9975]
    """
    A_noisy = A.copy()
    diag_delta = rng.uniform(-eps, eps, size=A.shape[0])

    for i in range(A.shape[0]):
        A_noisy[i, i] = A[i, i] * (1.0 + diag_delta[i])

    return A_noisy


def perturb_B_relative_bounded(B, eps, rng):
    """
    Bounded relative perturbation on B:

        B_noisy = B * (1 + Delta)
        Delta_ij ~ Uniform[-eps, eps]

    Zero entries remain zero, so the paper-style zero diagonal
    in the task block is preserved.
    """
    delta = rng.uniform(-eps, eps, size=B.shape)
    B_noisy = B * (1.0 + delta)
    return B_noisy


def relative_noise_test(A, B, K_fixed, noise_levels=(0.05,), trials=100, seed=0):
    """
    Robustness test with bounded relative perturbation on both A and B.

    A:
        perturb only diagonal entries by bounded ±eps.

    B:
        perturb entries by bounded ±eps relative perturbation.

    K_fixed:
        computed once from nominal A and B, then kept fixed.
    """
    rng = np.random.default_rng(seed)

    print("\n========== Bounded relative perturbation test on A and B ==========")
    print("A_noisy: diagonal(A) * (1 + delta), delta ~ Uniform[-eps, eps]")
    print("B_noisy = B * (1 + Delta), Delta ~ Uniform[-eps, eps]")
    print("K is fixed from the nominal A and nominal B.")

    for eps in noise_levels:
        max_eigs = []
        stable_count = 0

        for _ in range(trials):
            A_noisy = perturb_A_diagonal_bounded(A, eps, rng)
            B_noisy = perturb_B_relative_bounded(B, eps, rng)

            _, max_abs, stable = closed_loop_eigs(A_noisy, B_noisy, K_fixed)

            max_eigs.append(max_abs)
            stable_count += int(stable)

        print(f"\nBounded relative perturbation level on A and B: ±{eps * 100:.1f}%")
        print(f"Stable trials: {stable_count}/{trials}")
        print(f"Max |eig| mean: {np.mean(max_eigs):.6f}")
        print(f"Max |eig| max : {np.max(max_eigs):.6f}")
        print(f"Max |eig| min : {np.min(max_eigs):.6f}")


def single_worst_case_summary(A, B, K_fixed, eps=0.05, trials=1000, seed=2):
    """
    Stress summary:
    search many bounded relative perturbations on both A and B,
    and report the worst max |eig|.
    """
    rng = np.random.default_rng(seed)

    worst_max_abs = -np.inf
    worst_eigs = None
    stable_count = 0

    for _ in range(trials):
        A_noisy = perturb_A_diagonal_bounded(A, eps, rng)
        B_noisy = perturb_B_relative_bounded(B, eps, rng)

        eigvals, max_abs, stable = closed_loop_eigs(A_noisy, B_noisy, K_fixed)

        stable_count += int(stable)

        if max_abs > worst_max_abs:
            worst_max_abs = max_abs
            worst_eigs = eigvals

    print("\n========== Worst-case bounded perturbation summary ==========")
    print(f"Bounded relative perturbation level on A and B: ±{eps * 100:.1f}%")
    print(f"Trials: {trials}")
    print(f"Stable trials: {stable_count}/{trials}")
    print(f"Worst max |eig|: {worst_max_abs:.6f}")
    print("Worst-case eigenvalues:")
    print(worst_eigs)


def main():
    numtasks = 3

    A, B, Q, R = build_matrices(numtasks=numtasks)

    print("Task order: hist, stereo, mm")

    print("\nA =")
    print(A)

    print("\nB =")
    print(B)

    print("\nQ =")
    print(Q)

    print("\nR =")
    print(R)

    # Compute K once using nominal A and nominal B.
    K_nominal = solve_lqr_gain(A, B, Q, R)

    eigvals, max_abs, stable = closed_loop_eigs(A, B, K_nominal)

    print("\n========== Nominal closed-loop result ==========")
    print("K_nominal =")
    print(K_nominal)

    print("\nNominal closed-loop eigenvalues:")
    print(eigvals)

    print(f"\nNominal max |eig| = {max_abs:.6f}")
    print(f"Nominal stable = {stable}")

    # Srini requested 5% perturbation; now applied to both A and B.
    relative_noise_test(
        A,
        B,
        K_nominal,
        noise_levels=(0.05,),
        trials=100,
        seed=0,
    )

    # Stronger 1000-trial summary at bounded ±5% perturbation on A and B.
    single_worst_case_summary(
        A,
        B,
        K_nominal,
        eps=0.05,
        trials=1000,
        seed=2,
    )


if __name__ == "__main__":
    main()