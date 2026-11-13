"""Cek apakah Pyomo dapat memanggil solver HiGHS di environment aktif."""

def main():
    try:
        import pyomo.environ as pyo
    except Exception as exc:
        print("Pyomo belum dapat diimpor:", exc)
        return 1

    solver = pyo.SolverFactory("appsi_highs")
    available = solver.available(exception_flag=False)
    print("appsi_highs tersedia:", available)
    if not available:
        print("Jalankan: python -m pip install pyomo highspy")
        return 1

    model = pyo.ConcreteModel()
    model.x = pyo.Var(domain=pyo.NonNegativeReals)
    model.obj = pyo.Objective(expr=model.x, sense=pyo.minimize)
    model.c = pyo.Constraint(expr=model.x >= 5)
    result = solver.solve(model)
    print("termination:", result.solver.termination_condition)
    print("nilai x:", pyo.value(model.x))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
