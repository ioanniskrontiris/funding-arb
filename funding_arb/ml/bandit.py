import numpy as np

class LinTS:
    """
    Linear Thompson Sampling bandit.
    Actions are ints (e.g., 0..3). Feature vector x must be (d, 1).
    Reward = -execution_cost_bps (higher is better).
    """
    def __init__(self, d: int, actions: list[int], sigma2: float = 1.0, ridge: float = 1.0):
        self.d = d
        self.actions = actions
        self.sigma2 = sigma2
        self.A = {a: ridge * np.eye(d) for a in actions}
        self.b = {a: np.zeros((d, 1)) for a in actions}

    def _sample_theta(self, a: int):
        A_inv = np.linalg.inv(self.A[a])
        mu = A_inv @ self.b[a]
        cov = self.sigma2 * A_inv
        return np.random.multivariate_normal(mu.ravel(), cov).reshape(-1, 1)

    def choose(self, x: np.ndarray) -> int:
        scores = {a: float(self._sample_theta(a).T @ x) for a in self.actions}
        return max(scores, key=scores.get)

    def update(self, a: int, x: np.ndarray, reward: float):
        self.A[a] += x @ x.T
        self.b[a] += reward * x