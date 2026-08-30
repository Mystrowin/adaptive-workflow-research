# Paper build

The manuscript source is main.tex; references are in references.bib.
Run the analysis script first so that figures/ and tables/ exist:

~~~powershell
python analysis/make_publication_artifacts.py
~~~

To build the checked-in PDF from the repository root, run:

~~~powershell
python analysis/build_paper_pdf.py
~~~

If a LaTeX engine is installed, compile from this directory:

~~~powershell
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
~~~

The checked-in paper.pdf is the local preprint artifact. It is not a
conference acceptance or a journal publication. The build script records
whether native LaTeX or its deterministic ReportLab fallback produced it.
