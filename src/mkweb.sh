#!/bin/sh -e
version="$(PYTHONPATH=. python3 -c 'import apkfoundry; print(apkfoundry.VERSION)')"
cp -a docs/ target/
cp LICENSE* target/

cp README.rst target/index.rst
cat >>target/index.rst <<-'EOF'

More documentation
------------------

* `APKBUILD expectations <APKBUILD.html>`_
* `Configuration guide <configuration.html>`_
* `Design document <design.html>`_
* `GitLab CI guide <gitlab-ci.html>`_
* `Roadmap <todo.html>`_
* `GPL 2.0 license <LICENSE.html>`_
* `MIT license <LICENSE.MIT.html>`_
EOF

sed -i "s/^README for APK Foundry\$/& v$version/" target/index.rst

sed -E -i \
	-e 's@<README.rst>@<index.html>@g' \
	-e 's@<docs/([^>.]*).rst>@<\1.html>@g' \
	-e 's@<docs/(examples/[^>]*)>@<\1.html>@g' \
	target/*.rst

for i in target/LICENSE*; do
	printf '.. include:: %s\n  :literal:\n' \
	"${i##*/}" > "$i.rst"
done

for i in target/examples/*; do
	lang="${i##*.}"
	case "$lang" in
	yml) lang=yaml;;
	esac

	printf '.. include:: %s\n  :code: %s\n' \
	"${i##*/}" "$lang" > "$i.rst"
done

for i in target/*.rst target/examples/*.rst; do
	printf 'RST2HTML %s\n' "${i##*/}"
	rst2html5 -qt "$i" "${i%.rst}.html"
done

find target -type f -not -name \*.html -delete
