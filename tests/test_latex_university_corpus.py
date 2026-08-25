import math

import pytest

from plotter_processor.latex_renderer import MathTextRenderer


@pytest.mark.parametrize(
    "expression",
    [
        r"\frac{x^2+1}{x-1}",
        r"\sqrt{x^2+y^2}",
        r"\sqrt[3]{x+1}",
        r"\sum_{n=1}^{\infty}\frac{1}{n^2}",
        r"\prod_{k=1}^{m}k",
        r"\int_0^\infty x^2e^{-x}\,dx",
        r"\iint_A f(x,y)\,dx\,dy",
        r"\iiint_V f(x,y,z)\,dx\,dy\,dz",
        r"\lim_{x\to0}\frac{\sin x}{x}=1",
        r"\sin x+\cos x+\tan x+\cot x",
        r"\ln x+\log x+\exp x",
        r"\min_x f(x)+\max_x f(x)",
        r"\vec{F}=m\vec{a}",
        r"\hat{x}+\bar{x}+\overline{xy}",
        r"\underline{x}+\dot{x}+\ddot{x}",
        r"\mathbf{x}+\mathrm{d}x+\mathit{y}+\mathcal{F}",
        r"\text{where }x>0",
        r"\alpha+\beta=\gamma",
        r"\Gamma+\Delta+\Theta+\Lambda+\Omega",
        r"a\leq b\neq c\geq d\approx e\equiv f",
        r"A\rightarrow B\leftrightarrow C\Rightarrow D\Leftrightarrow E",
        r"x\mapsto f(x)\uparrow\downarrow",
        r"A\subseteq B\cap C\cup D\setminus E",
        r"x\in A, y\notin B, \emptyset\subset C",
        r"\forall x\in A\;\exists y\in B",
        r"\neg P\land Q\lor R",
        r"a\perp b\parallel c",
        r"\frac{\partial f}{\partial x}+\nabla f=\infty",
        r"\left(\frac{x+1}{x-1}\right)^2",
        r"f(x)=\frac{1}{\sigma\sqrt{2\pi}}e^{-\frac{(x-\mu)^2}{2\sigma^2}}",
    ],
)
def test_university_latex_subset_is_vector_first(expression: str) -> None:
    rendered = MathTextRenderer().render(expression, 5.0)

    assert rendered.quality["render_path"] == "vector-first"
    assert rendered.quality["quality_failures"] == ()
    assert rendered.strokes
    assert all(
        math.isfinite(point.x) and math.isfinite(point.y)
        for stroke in rendered.strokes
        for point in stroke.points
    )


def test_logic_aliases_are_normalized_without_user_macros() -> None:
    rendered = MathTextRenderer().render(r"P\land Q\lor R", 5.0)

    assert rendered.expression == r"P\wedge Q\vee R"
    assert rendered.quality["render_path"] == "vector-first"
