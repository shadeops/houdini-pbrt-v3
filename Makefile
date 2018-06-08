COVERAGE = coverage

hda:
	hotl -C otls/hda otls/pbrt.hda

package: hda
	/bin/rm -fv package/soho_pbrt-v3.zip
	mkdir -p package/
	zip -r package/soho_pbrt-v3.zip \
		otls/pbrt.hda \
		soho \
		vop \
		-x *.pyc
tests:
	hython tests/tests.py

coverage:
	hython $(COVERAGE) run --branch --source=soho/python2.7 tests/tests.py

clean:
	/bin/rm -fv ./soho/python2.7/*.pyc
	/bin/rm -fvr ./package
