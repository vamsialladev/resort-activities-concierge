# Contributing

1. Branch from `main` and open a pull request; CI must pass. Commits follow
   [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
2. **A new activity:** add a template to `src/concierge/seed.py` (`TEMPLATES`). The app adds it to the schedule on
   the next start. Check the eval cases that list that property's sessions.
3. **A new policy or FAQ entry:** add a `## ` section to a file in `data/docs/` (front matter: title, property),
   add a labelled question to `eval/retrieval.jsonl`, and run `python -m eval.run_eval --retrieval --hybrid`.
4. **Prompt or tool changes:** run the dev eval (3 runs) before and after and put both numbers in the PR. Run the
   held-out set only when you're done changing things.
5. **A new tool:** a plain function in `src/concierge/tools.py`, its schema in `SCHEMAS`, unit tests without the
   model, and eval cases for when it should and shouldn't be called.
6. Run `make check` before pushing.
