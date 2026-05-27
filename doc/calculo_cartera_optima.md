# Cálculo de la cartera óptima

El flujo completo pasa por tres etapas: **construcción de inputs** (μ y Σ), **preprocesamiento por estrategia** (ajuste de sentimiento) y **optimización de pesos**.

---

## Etapa 1 — Retornos esperados históricos (μ)

Para cada ticker se calcula el retorno anual promedio histórico a partir de precios de cierre del último año:

```
μ[i] = retorno_historico_anual(precio_cierre[i])
```

Implementado con `expected_returns.mean_historical_return(prices_df)` de PyPortfolioOpt.

---

## Etapa 2 — Matriz de covarianza (Σ)

Se calcula la covarianza muestral de los retornos diarios:

```
Σ = cov_muestral(retornos_diarios)
```

Captura tanto la volatilidad individual de cada activo como las correlaciones entre ellos.

---

## Etapa 3 — Preprocesamiento por estrategia

Cada estrategia implementa un hook `preprocess(μ, Σ, sentiment_map, λ) → (μ', Σ')` que decide cómo incorporar el sentimiento antes de construir la frontera eficiente.

### 3a. MaxSharpeStrategy — ajuste de retornos esperados

Modifica **μ** proporcionalmente al score de sentimiento de cada ticker. La definición elemento a elemento es:

$$
\mu_{\text{adj},i} = \mu_i \cdot (1 + \lambda \cdot s_i)
$$

En forma vectorial compacta:

$$
\mu_{\text{adj}} = \mu \odot (\mathbf{1} + \lambda \cdot s)
$$

donde:

- $s \in [-1, 1]^n$ — vector de scores de sentimiento por ticker
- $\lambda = 0.15$ — configurable vía `SENTIMENT_LAMBDA`
- $\mathbf{1}$ — vector de unos
- $\odot$ — producto elemento a elemento (Hadamard)
- **Σ queda sin cambios**

**Ejemplo con sentimiento positivo** (`s = 0.8`):

$$
\mu_{\text{adj}}[\text{AAPL}] = 0.20 \cdot (1 + 0.15 \times 0.8) = 0.20 \times 1.12 = 0.224 \quad (+2.4\text{ pp})
$$

**Ejemplo con sentimiento negativo** (`s = -0.5`):

$$
\mu_{\text{adj}}[X] = \mu[X] \cdot (1 + 0.15 \times (-0.5)) = \mu[X] \times 0.925 \quad (-7.5\%)
$$

Cuando `use_sentiment=False` o la estrategia es `MinVolatilityStrategy`, este ajuste no se aplica y μ queda inalterado.

### 3b. MinVolatilitySentimentStrategy — escalado de la diagonal de Σ

En lugar de ajustar μ, escala la **varianza individual** de cada activo según el sentimiento. La definición elemento a elemento es:

$$
\tilde{\Sigma}_{ij} =
\begin{cases}
\Sigma_{ii} \cdot (1 - \lambda \cdot s_i) & \text{si } i = j \\
\Sigma_{ij} & \text{si } i \neq j
\end{cases}
$$

En forma matricial compacta, definiendo $\sigma^2 = \text{diag}(\Sigma)$ (vector de varianzas):

$$
\tilde{\Sigma} = \Sigma - \text{diag}(\lambda \cdot s \odot \sigma^2)
$$

donde $\odot$ es el producto elemento a elemento (Hadamard). Se resta a Σ una matriz diagonal cuyos elementos son $\lambda \cdot s_i \cdot \Sigma_{ii}$, dejando todas las covarianzas fuera de la diagonal intactas.

Los elementos fuera de la diagonal (covarianzas entre pares) se mantienen sin cambios.

- Sentimiento **positivo** (`s[i] > 0`): reduce la varianza percibida → el optimizador ve al activo como menos riesgoso → le asigna mayor peso
- Sentimiento **negativo** (`s[i] < 0`): infla la varianza percibida → el optimizador penaliza al activo → le asigna menor peso
- **μ queda sin cambios** — la estrategia no toca los retornos esperados

**Ejemplo** con `λ = 0.15`:

| Ticker | s[i] | Factor | Efecto sobre Σ̃[i,i] |
|--------|------|--------|----------------------|
| AAPL   | +0.8 | 0.88   | −12% varianza percibida |
| MSFT   | −0.5 | 1.075  | +7.5% varianza percibida |
| GOOGL  |  0.0 | 1.00   | sin cambio |

### 3c. MinVolatilityStrategy — sin ajuste

No modifica ni μ ni Σ. Devuelve los inputs tal como vienen de las etapas 1 y 2.

---

## Etapa 4 — Optimización de pesos

Dependiendo de la estrategia, se resuelve uno de los dos problemas siguientes.

### Max Sharpe

$$
\max_{w} \frac{w^\top \mu' - r_f}{\sqrt{w^\top \Sigma w}}
\quad \text{s.t.} \quad \sum_i w_i = 1, \quad w_i \geq 0
$$

donde `μ'` es el μ original o ajustado según `use_sentiment`, y `rf = 0.05`.

### Min Volatility (con o sin ajuste de Σ)

$$
\min_{w} \sqrt{w^\top \tilde{\Sigma} w}
\quad \text{s.t.} \quad \sum_i w_i = 1, \quad w_i \geq 0
$$

donde `Σ̃` es la covarianza original (`MinVolatilityStrategy`) o con diagonal escalada (`MinVolatilitySentimentStrategy`).

---

## Resumen de estrategias

| Estrategia | Objetivo | Ajuste de μ | Ajuste de Σ | `use_sentiment` |
|---|---|---|---|---|
| `max_sharpe` | Maximiza Sharpe | Sí (`μ_adj`) | No | opcional |
| `min_volatility` | Minimiza varianza | No | No | ignorado |
| `min_vol_sentiment` | Minimiza varianza | No | Sí (diagonal) | requerido |

---

## Por qué el sentimiento produce pesos distintos

**En MaxSharpe**: al modificar μ, el punto de máximo Sharpe se desplaza sobre la frontera eficiente. Un ticker con sentimiento positivo tiene `μ_adj` más alto → mayor contribución al numerador del Sharpe → mayor peso asignado.

**En MinVolatilitySentiment**: al escalar la diagonal de Σ, el optimizador percibe mayor riesgo en activos con noticias negativas y los evita, aunque μ no cambie. El punto de mínima varianza se desplaza sobre la frontera sin alterar las expectativas de retorno.

---

## Resultado

`OptimizedWeights` expone los resultados de la estrategia ejecutada:

| Campo | Descripción |
|---|---|
| `weights` | Pesos óptimos por ticker |
| `expected_annual_return` | Retorno anual esperado del portfolio optimizado |
| `annual_volatility` | Volatilidad anual del portfolio |
| `sharpe_ratio` | Ratio de Sharpe resultante |
| `expected_returns_per_ticker` | μ' por ticker (muestra el efecto del sentimiento en MaxSharpe) |
| `optimization_strategy` | Nombre de la estrategia usada (`max_sharpe` / `min_volatility` / `min_vol_sentiment`) |
