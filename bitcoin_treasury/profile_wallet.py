from pathlib import Path

from odoo.tools.profiler import Profiler


def main(env):
    wallets = env["bitcoin.wallet"].search([])
    if not wallets:
        raise RuntimeError("No bitcoin.wallet records found.")

    output_path = Path("/home/elmeri/profile/refresh.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    profiler = Profiler(
        db=None,
        description=f"bitcoin.wallet.refresh {wallets.ids}",
        collectors=["sql", "traces_async"],
    )
    try:
        with profiler:
            wallets.refresh()
    finally:
        output_path.write_text(profiler.json(), encoding="utf-8")
        env.cr.rollback()
        print(f"Wrote profile to {output_path}")
        print("Rolled back refresh database changes.")


main(env)
