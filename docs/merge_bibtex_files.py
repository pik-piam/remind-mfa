def on_startup(command, dirty):
    f1 = open('docs/mrmfa_sources.bib', encoding='utf-8').read()
    f2 = open('docs/custom_refs.bib', encoding='utf-8').read()
    open('docs/all_refs.bib','w', encoding='utf-8').write(f1+'\n'+f2)
