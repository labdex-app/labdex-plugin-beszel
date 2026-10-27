# Beszel

A [labdex](https://github.com/reykimedev/labdex) plugin. Host status from Beszel agents (online or down), with CPU, memory and disk on each host page. Adds hosts as Beszel systems (plan, then apply) and rolls the agent out over Ansible.

**Version** 1.0 · **Works with** labdex >=1.0,<2 · **Plugin id** `beszel`

> [!WARNING]
> Built with AI, for home labs only: labdex and its plugins were written largely with an AI
> coding assistant (Claude), directed and reviewed by a human. They haven't had an independent
> security audit and may contain security problems. Run them on a trusted home network.

## Install

It ships with labdex: **Plugins › Marketplace**, then *Install* (nothing is downloaded). Updates arrive through the official Marketplace (signed with the labdex project key).

## Settings

| Setting | Notes |
| --- | --- |
| Hub URL |  |
| User (email) | A Beszel user; systems it creates belong to it |
| Password |  |
| Check the TLS certificate |  |
| Hub public key | ssh-ed25519 … from Beszel's “Add system” dialog; the agent only accepts this hub |
| Agent port |  |
| Universal token | Optional: lets agents connect to the hub themselves (with the hub URL) |
| SSH user (agent install) |  |
| SSH private key (agent install) | Pick a global secret to share one key between modules |
| Check SSH host keys |  |

## Actions

- **Check connection** (run)
- **Read host status** (run)
- **Add hosts as systems** (plan): Every host this instance applies to that Beszel doesn't know yet
- **Install the agent** (run): Downloads Beszel's install script on the host and runs it with the hub key (and token)

## Releasing

Bump `version` in `plugin.yaml`, add a `## <version>` section to `CHANGELOG.md`, commit, then
publish a GitHub release tagged `v<version>` (web UI, or `gh release create v<version> --target main --notes ""`).
The release workflow signs the plugin with the `LABDEX_SIGNING_KEY` secret, attaches the zip and
`CHANGELOG.md` to the release and puts that version's CHANGELOG section into its description.
Files listed in `.releaseignore` stay out of the zip.
