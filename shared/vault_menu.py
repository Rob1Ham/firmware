# vault_menu.py - minimal Vault co-signer configuration menu (test-only).
#
# Entry point: Spending Policy submenu -> 'Vault Co-Sign' (wired in flow.py).
# Deliberately minimal: no warning screens, no dramatic pauses.
# Rule layer is vault_policy.py; glue/NVS handling is vault.py; this file
# is only UX for editing the settings key 'vault'.
#
# Menu items (per docs/vault_progress.md task list):
#   - Vault Mode on/off (refused until a valid policy is enrolled)
#   - Enroll Policy: JSON file pushed over USB / from SD card
#   - Cadence N, Max Fee (sats), Exit Destination, Commitment Root
#   - Wipe Policy
from ux import ux_show_story, ux_confirm, ux_enter_number, the_ux
from menu import MenuSystem, MenuItem
from charcodes import KEY_CANCEL

import vault


class VaultConfigMenu(MenuSystem):

    def __init__(self):
        items = self.construct()
        super().__init__(items)

    def update_contents(self):
        self.replace_items(self.construct())

    @classmethod
    async def be_a_submenu(cls, *a):
        return cls()

    def construct(self):
        cfg = vault._cfg()
        enrolled = bool(cfg)
        on = bool(cfg.get('enabled'))
        items = [
            MenuItem(('[ON] ' if on else '[OFF] ') + 'Vault Mode',
                     f=self.toggle_enable),
            MenuItem('Enroll Policy', f=self.enroll_policy),
            MenuItem('Cadence N', f=self.set_n),
            MenuItem('Max Fee (sats)', f=self.set_fee),
            MenuItem('Exit Destination', f=self.show_exit),
            MenuItem('Show Commitment Root', f=self.show_root),
        ]
        if enrolled:
            items.append(MenuItem('Wipe Policy', f=self.wipe))
        return items

    async def toggle_enable(self, *a):
        # set_enabled refuses to turn on until validate_cfg passes.
        res, msg = vault.set_enabled(not vault.is_enabled())
        if not res:
            await ux_show_story('Cannot change vault mode:\n\n%s' % msg,
                                title='VAULT')
            return
        self.update_contents()

    async def enroll_policy(self, *a):
        # Read a JSON policy file (USB push / SD) and store it as the vault
        # cfg. Enrolls dark: 'enabled' is forced off; the user reviews the
        # fields and flips Vault Mode on explicitly.
        from actions import file_picker
        from files import CardSlot
        from ux import import_export_prompt
        import json

        choice = await import_export_prompt('Vault policy JSON',
                                            is_import=True, no_qr=True)
        if choice == KEY_CANCEL or not isinstance(choice, dict):
            return

        fn = await file_picker(suffix=['.json'], min_size=10, max_size=8192,
                               none_msg='Policy JSON file needed', **choice)
        if not fn:
            return

        with CardSlot(readonly=True, **choice) as card:
            with open(fn, 'rt') as fd:
                raw = fd.read()

        try:
            cfg = json.loads(raw)
            if not isinstance(cfg, dict):
                raise ValueError('not an object')
        except Exception as e:
            await ux_show_story('Not a valid policy file: %s' % e,
                                title='VAULT')
            return

        res, msg = vault.validate_cfg(cfg)
        if not res:
            await ux_show_story('Policy rejected:\n\n%s' % msg, title='VAULT')
            return

        cfg['enabled'] = 0
        try:
            vault.save_cfg(cfg)
        except Exception as e:
            await ux_show_story('Cannot save policy: %s' % e, title='VAULT')
            return
        vault.vault_log('CFG enrolled')
        await ux_show_story('Vault policy enrolled (disabled).\n\n'
                            'Review Cadence N / Max Fee / Exit Destination,\n'
                            'then enable Vault Mode.', title='VAULT')
        self.update_contents()

    async def set_n(self, *a):
        cfg = vault._cfg()
        val = await ux_enter_number('Cadence N (blocks):', max_value=0xFFFF,
                                    value=cfg.get('n', 1008))
        if not val:
            return
        cfg['n'] = int(val)
        vault.save_cfg(cfg)
        vault.vault_log('CFG n=%d' % cfg['n'])
        self.update_contents()

    async def set_fee(self, *a):
        cfg = vault._cfg()
        val = await ux_enter_number('Max fee (sats):', max_value=1000000,
                                    value=cfg.get('f0_max', 10000))
        if not val:
            return
        cfg['f0_max'] = int(val)
        vault.save_cfg(cfg)
        vault.vault_log('CFG f0_max=%d' % cfg['f0_max'])
        self.update_contents()

    async def show_exit(self, *a):
        cfg = vault._cfg()
        await ux_show_story('Exit destination spk:\n\n%s'
                            % (cfg.get('exit_spk') or '(not set)'),
                            title='VAULT')

    async def show_root(self, *a):
        # Lattice commitment root is enrolled by the (pending) lattice
        # flow; show whatever is stored, if anything.
        cfg = vault._cfg()
        root = cfg.get('lattice_root')
        await ux_show_story('Lattice commitment root:\n\n%s'
                            % (root or '(lattice not yet enrolled)'),
                            title='VAULT')

    async def wipe(self, *a):
        if not await ux_confirm('Wipe vault policy?'):
            return
        vault.wipe()
        vault.vault_log('CFG wiped')
        self.update_contents()


async def vault_feature_menu(*a):
    # Entry point wired into the Spending Policy submenu (flow.py).
    the_ux.push(VaultConfigMenu())

# EOF
