
cwd=`pwd`

remove_templates()
{
   name=$1

   if test -f $cwd/softwares/$name/data/install-templates.txt; then
       for template in `cat $cwd/softwares/$name/data/install-$name-templates.txt`
       do
           echo "removing $template"
           rm -rf $template
       done
   fi
   
}
