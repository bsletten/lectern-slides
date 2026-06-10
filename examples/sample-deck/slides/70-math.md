# Typeset Math

Inline math flows in text: the attention weights are a softmax over $QK^\top$,
scaled by $\sqrt{d_k}$ to keep gradients stable.

Display math gets its own block:

$$
\mathrm{Attention}(Q, K, V) = \mathrm{softmax}\!\left(\frac{Q K^\top}{\sqrt{d_k}}\right) V
$$

And a classic, for good measure:

$$
P(A \mid B) = \frac{P(B \mid A)\, P(A)}{P(B)}
$$
