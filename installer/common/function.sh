
cwd=`pwd`

remove_templates()
{
   name=$1
   comp_name=$2

   if test -f $cwd/softwares/$name/data/install-$comp_name-templates.txt; then
       for template in `cat $cwd/softwares/$name/data/install-$comp_name-templates.txt`
       do
           echo "removing $template"
           rm -rf $template
       done
   fi
   
}

create_datadir()
{
   name=$1

   if test ! -d $cwd/softwares/$name/data; then
      mkdir $cwd/softwares/$name/data
   fi
}

