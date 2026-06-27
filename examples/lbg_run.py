import limitedbg as lbg

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
def main() -> None:
# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
    chain = lbg.Chain(exp_age=9)
    chain.dry_run(periods=100)
    chain.run(periods=500)
    chain.dump_log()

# ----- ----- ----- ----- ----- ----- ----- ----- ----- -----
if __name__ == '__main__':
    main()
